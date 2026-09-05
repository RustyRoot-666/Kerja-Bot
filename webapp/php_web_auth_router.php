<?php

declare(strict_types=1);
require_once __DIR__.'/php_backend.php';
require_once __DIR__.'/php_auth.php';
require_once __DIR__.'/php_superadmin_view_fix.php';
require_once __DIR__.'/php_area_success.php';
auth_ensure_schema();

function web_auth_respond(mixed $payload,int $status=200):never{http_response_code($status);header('Content-Type: application/json; charset=utf-8');header('Cache-Control: no-store, no-cache, must-revalidate, max-age=0');echo json_encode($payload,JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES);exit;}
function web_auth_input():array{$d=json_decode(file_get_contents('php://input')?:'{}',true);return is_array($d)?$d:[];}
function web_auth_same_origin(): void {
    $origin=trim((string)($_SERVER['HTTP_ORIGIN']??''));
    if($origin==='')return;
    $parsed=parse_url($origin);
    if(!is_array($parsed)||empty($parsed['scheme'])||empty($parsed['host']))web_auth_respond(['ok'=>false,'error'=>'invalid_origin','message'=>'Permintaan ditolak.'],403);
    $originScheme=strtolower((string)$parsed['scheme']);
    $originHost=strtolower((string)$parsed['host']);
    $originPort=isset($parsed['port'])?(int)$parsed['port']:null;
    $forwardedProto=strtolower(trim(explode(',',(string)($_SERVER['HTTP_X_FORWARDED_PROTO']??''))[0]??''));
    $serverScheme=$forwardedProto!==''?$forwardedProto:((!empty($_SERVER['HTTPS'])&&$_SERVER['HTTPS']!=='off')?'https':'http');
    $serverHost=strtolower(trim(explode(',',(string)($_SERVER['HTTP_X_FORWARDED_HOST']??''))[0]??''));
    if($serverHost==='')$serverHost=strtolower((string)($_SERVER['HTTP_HOST']??''));
    $serverHost=preg_replace('/:\\d+$/','',$serverHost)?:$serverHost;
    $allowedHosts=['app.botkerja.web.id'];
    $currentHost=preg_replace('/:\\d+$/','',strtolower((string)($_SERVER['HTTP_HOST']??'')));
    if($currentHost!=='')$allowedHosts[]=$currentHost;
    $originPortAllowed=$originPort===null||($originScheme==='https'&&$originPort===443)||($originScheme==='http'&&$originPort===80);
    if($originScheme!==$serverScheme||!in_array($originHost,$allowedHosts,true)||!$originPortAllowed)web_auth_respond(['ok'=>false,'error'=>'invalid_origin','message'=>'Permintaan ditolak.'],403);
}

// Supervisor means an admin/superadmin account or the two configured supervisor NIKs.
// Keep this local to the web router so /api/web/open-orders never depends on an
// optional helper file defining the function.
function report_is_supervisor(?array $tech): bool {
    if (!$tech) return false;
    $nik = trim((string)($tech['nik'] ?? ''));
    if (in_array($nik, ['91260038','94250015'], true)) return true;
    $role = strtolower(trim((string)($tech['role'] ?? '')));
    if (in_array($role, ['admin','superadmin'], true)) return true;
    try {
        $st = db()->prepare('SELECT role FROM technicians WHERE id=? LIMIT 1');
        $st->execute([(int)($tech['id'] ?? 0)]);
        $dbRole = strtolower(trim((string)$st->fetchColumn()));
        return in_array($dbRole, ['admin','superadmin'], true);
    } catch (Throwable $e) {
        return false;
    }
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
    if(empty($tech['password_hash']))web_auth_respond(['ok'=>false,'error'=>'password_not_set','message'=>'Password awal harus dibuat oleh Bot Telegram.'],400);
    if(strlen($new)<8)web_auth_respond(['ok'=>false,'error'=>'password_too_short','message'=>'Password baru minimal 8 karakter.'],400);
    if(strlen($new)>128)web_auth_respond(['ok'=>false,'error'=>'password_too_long','message'=>'Password baru maksimal 128 karakter.'],400);
    if($new!==$confirm)web_auth_respond(['ok'=>false,'error'=>'password_mismatch','message'=>'Konfirmasi password tidak sama.'],400);
    if(!auth_password_verify($current,(string)$tech['password_hash']))web_auth_respond(['ok'=>false,'error'=>'current_password_invalid','message'=>'Password saat ini salah.'],400);
    if(auth_password_verify($new,(string)$tech['password_hash']))web_auth_respond(['ok'=>false,'error'=>'same_password','message'=>'Password baru harus berbeda dari password saat ini.'],400);
    db()->prepare('UPDATE technicians SET password_hash=? WHERE id=? AND is_active=1')->execute([auth_password_hash($new),(int)$tech['id']]);
    web_auth_respond(['ok'=>true,'message'=>'Password berhasil diubah.']);
}
if($path==='/api/auth/logout'&&$method==='POST'){auth_logout();web_auth_respond(['ok'=>true]);}
if($path==='/api/web/my-report'&&$method==='GET'){$tech=auth_require(['technician','admin','superadmin']);require_once __DIR__.'/php_orderanku_fix.php';$result=load_report_for_viewer_php((int)$tech['telegram_id'],'');web_auth_respond($result,($result['ok']??false)?200:404);}
if($path==='/api/web/open-orders'&&$method==='GET'){$tech=auth_require(['technician','admin','superadmin']);require_once __DIR__.'/php_orderanku_fix.php';require_once __DIR__.'/php_unified_workflow.php';if(report_is_supervisor($tech)){$result=superadmin_open_orders_php(false);}else{$result=load_orders_for_viewer_php((int)$tech['telegram_id'],'',false);}if($result['ok']??false)$result=unified_enrich_open_orders_result($result,(int)$tech['telegram_id']);web_auth_respond($result,($result['ok']??false)?200:404);}
if($path==='/api/web/dashboard'&&$method==='GET'){$tech=auth_require(['admin','superadmin']);web_auth_respond(load_superadmin_dashboard_php((string)($_GET['area']??'ALL'),(string)($_GET['period']??'daily')));}
if($path==='/api/web/area-success'&&$method==='GET'){$tech=auth_require(['admin','superadmin']);web_auth_respond(area_success_snapshot());}
return;
