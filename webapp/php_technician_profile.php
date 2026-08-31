<?php

declare(strict_types=1);

function technician_profile_get(int $telegramId): array {
    $tech = technician_by_telegram($telegramId);
    if (!$tech) return ['ok'=>false,'error'=>'technician_not_registered','message'=>'Akun Telegram belum terdaftar sebagai teknisi.'];

    $username='';
    if (table_exists('technician_usernames')) {
        try {
            $st=db()->prepare('SELECT username FROM technician_usernames WHERE telegram_id=? LIMIT 1');
            $st->execute([$telegramId]);
            $username=ltrim(trim((string)($st->fetchColumn() ?: '')),'@');
        } catch (Throwable) {}
    }

    return ['ok'=>true,'profile'=>[
        'telegram_id'=>$telegramId,
        'nik'=>trim((string)($tech['nik']??'')),
        'name'=>trim((string)($tech['name']??'')),
        'sto'=>strtoupper(trim((string)($tech['sto']??''))),
        'username'=>$username,
    ]];
}

function technician_profile_save(array $payload): array {
    $raw=trim((string)($payload['telegram_id']??''));
    if(!ctype_digit($raw)) return ['ok'=>false,'error'=>'invalid_request','message'=>'Telegram ID tidak valid.'];
    $telegramId=(int)$raw;
    $tech=technician_by_telegram($telegramId);
    if(!$tech) return ['ok'=>false,'error'=>'technician_not_registered','message'=>'Akun Telegram belum terdaftar sebagai teknisi.'];

    $name=trim(preg_replace('/\s+/',' ',(string)($payload['name']??'')) ?: '');
    $sto=strtoupper(trim((string)($payload['sto']??'')));
    $username=ltrim(trim((string)($payload['username']??'')),'@');
    $nameLen=strlen($name);

    if($name==='' || $nameLen<3 || $nameLen>80) return ['ok'=>false,'error'=>'invalid_name','message'=>'Nama harus 3-80 karakter.'];
    if($sto!=='' && !preg_match('/^[A-Z0-9]{2,8}$/',$sto)) return ['ok'=>false,'error'=>'invalid_sto','message'=>'Format STO tidak valid.'];
    if($username!=='' && !preg_match('/^[A-Za-z0-9_]{5,32}$/',$username)) return ['ok'=>false,'error'=>'invalid_username','message'=>'Username Telegram tidak valid.'];

    db()->beginTransaction();
    try {
        $st=db()->prepare('UPDATE technicians SET name=?, sto=? WHERE telegram_id=?');
        $st->execute([$name,$sto,$telegramId]);

        if(table_exists('technician_usernames')) {
            $cols=technician_master_columns('technician_usernames');
            if(in_array('telegram_id',$cols,true) && in_array('username',$cols,true)) {
                $up=db()->prepare("INSERT INTO technician_usernames(telegram_id,username) VALUES(?,?) ON CONFLICT(telegram_id) DO UPDATE SET username=excluded.username");
                try { $up->execute([$telegramId,$username]); }
                catch(Throwable) {
                    $u=db()->prepare('UPDATE technician_usernames SET username=? WHERE telegram_id=?');
                    $u->execute([$username,$telegramId]);
                    if($u->rowCount()===0) {
                        try { db()->prepare('INSERT INTO technician_usernames(telegram_id,username) VALUES(?,?)')->execute([$telegramId,$username]); } catch(Throwable) {}
                    }
                }
            }
        }

        db()->commit();
    } catch(Throwable $e) {
        if(db()->inTransaction()) db()->rollBack();
        throw $e;
    }

    try {
        if(table_exists('technician_master')) {
            $nik=trim((string)($tech['nik']??''));
            if($nik!=='') {
                $m=db()->prepare("UPDATE technician_master SET canonical_name=?, username=?, sto=?, updated_at=datetime('now') WHERE nik=?");
                $m->execute([technician_master_clean_name($name),$username,$sto,$nik]);
                technician_master_learn_alias($nik,$name,'profile');
            }
        }
    } catch(Throwable $e) {
        error_log('[miniapp-php] profile master sync skipped: '.$e->getMessage());
    }

    return technician_profile_get($telegramId) + ['saved'=>true];
}
