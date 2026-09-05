<?php

declare(strict_types=1);
require_once __DIR__.'/php_backend.php';
require_once __DIR__.'/php_auth.php';
auth_ensure_schema();

function web_auth_respond(mixed $payload,int $status=200):never{http_response_code($status);header('Content-Type: application/json; charset=utf-8');header('Cache-Control: no-store, no-cache, must-revalidate, max-age=0');echo json_encode($payload,JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES);exit;}
function web_auth_input():array{$d=json_decode(file_get_contents('php://input')?:'{}',true);return is_array($d)?$d:[];}
function web_auth_same_origin(): void {
    $origin=trim((string)($_SERVER['HTTP_ORIGIN']??''));
    if($origin==='')return;
    $expected=((!empty($_SERVER['HTTPS'])&&$_SERVER['HTTPS']!=='off')?'https':'http').'://'.($_SERVER['HTTP_HOST']??'');
    if($expected!==''&&rtrim($origin,'/')!==rtrim($expected,'/'))web_auth_respond(['ok'=>false,'error'=>'invalid_origin','message'=>'Permintaan ditolak.'],403);
}

$path=parse_url($_SERVER['REQUEST_URI']??'',PHP_URL_PATH)?:'';$method=strtoupper($_SERVER['REQUEST_METHOD']??'GET');
if($path==='/website'||$path==='/website/'){
    header('Content-Type: text/html; charset=utf-8');header('Cache-Control: no-store');readfile(__DIR__.'/website/index.html');exit;
}
if($path==='/api/auth/link/request'&&$method==='POST'){
    $p=web_auth_input();$id=trim((string)($p['telegram_id']??''));if(!ctype_digit($id))web_auth_respond(['ok'=>false,'error'=>'telegram_id_required','message'=>'Telegram ID tidak valid.'],400);
    $result=auth_request_link((int)$id);if(!($result['ok']??false))web_auth_respond($result,404);$token=(string)$result['token'];
    if(!auth_send_telegram_confirmation((int)$id,$token)){db()->prepare("UPDATE web_link_requests SET status='cancelled' WHERE token_hash=?")->execute([auth_hash_token($token)]);web_auth_respond(['ok'=>false,'error'=>'telegram_delivery_failed','message'=>'Bot gagal mengirim pesan Telegram. Pastikan bot sudah pernah dibuka oleh akun tersebut.'],502);}
    web_auth_respond(['ok'=>true,'token'=>$token,'expires_at'=>$result['expires_at'],'technician'=>$result['technician']]);
}
if($path==='/api/auth/link/status'&&$method==='GET'){web_auth_respond(auth_link_status(trim((string)($_GET['token']??''))));}
if($path==='/api/auth/login'&&$method==='POST'){$p=web_auth_input();$result=auth_login(trim((string)($p['nik']??'')),(string)($p['password']??''));web_auth_respond($result,($result['ok']??false)?200:401);}
if($path==='/api/auth/me'&&$method==='GET'){$tech=auth_current();if(!$tech)web_auth_respond(['ok'=>false,'error'=>'unauthorized'],401);web_auth_respond(['ok'=>true,'technician'=>['id'=>(int)$tech['id'],'telegram_id'=>(int)$tech['telegram_id'],'nik'=>$tech['nik'],'name'=>$tech['name'],'sto'=>$tech['sto'],'role'=>$tech['role'],'has_password'=>!empty($tech['password_hash'])]]);}
if($path==='/api/auth/password'&&$method==='POST'){
    web_auth_same_origin();
    $tech=auth_require();
    $p=web_auth_input();
    $current=(string)($p['current_password']??'');
    $new=(string)($p['new_password']??'');
    $confirm=(string)($p['confirm_password']??'');
    if(strlen($new)<8)web_auth_respond(['ok'=>false,'error'=>'password_too_short','message'=>'Password baru minimal 8 karakter.'],400);
    if($new!==$confirm)web_auth_respond(['ok'=>false,'error'=>'password_mismatch','message'=>'Konfirmasi password tidak sama.'],400);
    if(!empty($tech['password_hash'])&&!auth_password_verify($current,(string)$tech['password_hash']))web_auth_respond(['ok'=>false,'error'=>'current_password_invalid','message'=>'Password saat ini salah.'],400);
    if($current!==''&&auth_password_verify($new,(string)$tech['password_hash']))web_auth_respond(['ok'=>false,'error'=>'same_password','message'=>'Password baru harus berbeda dari password saat ini.'],400);
    db()->prepare('UPDATE technicians SET password_hash=? WHERE id=?')->execute([auth_password_hash($new),(int)$tech['id']]);
    web_auth_respond(['ok'=>true,'message'=>empty($tech['password_hash'])?'Password website berhasil dibuat.':'Password berhasil diubah.']);
}
if($path==='/api/auth/logout'&&$method==='POST'){auth_logout();web_auth_respond(['ok'=>true]);}
if($path==='/api/web/my-report'&&$method==='GET'){$tech=auth_require(['technician','admin','superadmin']);require_once __DIR__.'/php_orderanku_fix.php';$result=load_report_for_viewer_php((int)$tech['telegram_id'],'');web_auth_respond($result,($result['ok']??false)?200:404);}
if($path==='/api/web/open-orders'&&$method==='GET'){$tech=auth_require(['technician','admin','superadmin']);require_once __DIR__.'/php_orderanku_fix.php';require_once __DIR__.'/php_unified_workflow.php';$result=load_orders_for_viewer_php((int)$tech['telegram_id'],'',false);if($result['ok']??false)$result=unified_enrich_open_orders_result($result,(int)$tech['telegram_id']);web_auth_respond($result,($result['ok']??false)?200:404);}
if($path==='/api/web/dashboard'&&$method==='GET'){$tech=auth_require(['admin','superadmin']);web_auth_respond(load_dashboard_php((string)($_GET['area']??'ALL'),(string)($_GET['period']??'daily')));}
return;
