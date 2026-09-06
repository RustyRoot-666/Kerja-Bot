<?php

declare(strict_types=1);

function location_ensure_schema(): void {
    $pdo = db();
    $pdo->exec("CREATE TABLE IF NOT EXISTS technician_current_locations (
        technician_id INTEGER PRIMARY KEY,
        telegram_id INTEGER NOT NULL UNIQUE,
        latitude REAL NOT NULL,
        longitude REAL NOT NULL,
        accuracy REAL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(technician_id) REFERENCES technicians(id) ON DELETE CASCADE
    )");
    $pdo->exec('CREATE INDEX IF NOT EXISTS idx_tech_locations_updated ON technician_current_locations(updated_at)');
    $pdo->exec("CREATE TABLE IF NOT EXISTS technician_presence (
        technician_id INTEGER PRIMARY KEY,
        telegram_id INTEGER NOT NULL UNIQUE,
        last_seen TEXT NOT NULL,
        FOREIGN KEY(technician_id) REFERENCES technicians(id) ON DELETE CASCADE
    )");
    $pdo->exec('CREATE INDEX IF NOT EXISTS idx_tech_presence_seen ON technician_presence(last_seen)');
}

function location_iso_now(): string {
    return date('Y-m-d H:i:s');
}

function location_bot_token(): string {
    return trim((string)(getenv('BOT_TOKEN') ?: getenv('TELEGRAM_BOT_TOKEN') ?: ''));
}

function location_telegram_id_from_init_data(string $initData): int {
    $token = location_bot_token();
    if ($token === '' || trim($initData) === '') return 0;
    parse_str($initData, $data);
    $hash = (string)($data['hash'] ?? '');
    $authDate = (int)($data['auth_date'] ?? 0);
    if ($hash === '' || $authDate <= 0 || abs(time() - $authDate) > 86400) return 0;
    unset($data['hash']);
    ksort($data);
    $pairs = [];
    foreach ($data as $key => $value) $pairs[] = $key.'='.$value;
    $checkString = implode("\n", $pairs);
    $secret = hash_hmac('sha256', $token, 'WebAppData', true);
    $calculated = hash_hmac('sha256', $checkString, $secret);
    if (!hash_equals($hash, $calculated)) return 0;
    $user = json_decode((string)($data['user'] ?? ''), true);
    return is_array($user) ? (int)($user['id'] ?? 0) : 0;
}

function location_save_presence_from_init_data(string $initData): array {
    $telegramId = location_telegram_id_from_init_data($initData);
    if ($telegramId <= 0) return ['ok'=>false,'error'=>'invalid_telegram_webapp','message'=>'Identitas Telegram Mini App tidak valid.'];
    location_ensure_schema();
    $st = db()->prepare('SELECT id,name,nik,sto,is_active FROM technicians WHERE telegram_id=? LIMIT 1');
    $st->execute([$telegramId]);
    $tech = $st->fetch();
    if (!$tech || !(int)$tech['is_active']) return ['ok'=>false,'error'=>'technician_not_active','message'=>'Teknisi tidak aktif.'];
    $now = location_iso_now();
    db()->prepare('INSERT INTO technician_presence(technician_id,telegram_id,last_seen) VALUES(?,?,?) ON CONFLICT(technician_id) DO UPDATE SET telegram_id=excluded.telegram_id,last_seen=excluded.last_seen')->execute([(int)$tech['id'],$telegramId,$now]);
    return ['ok'=>true,'last_seen'=>$now,'technician'=>['id'=>(int)$tech['id'],'telegram_id'=>$telegramId,'name'=>$tech['name'],'nik'=>$tech['nik'],'sto'=>$tech['sto']]];
}

function location_save_from_init_data(string $initData, float $latitude, float $longitude, ?float $accuracy = null): array {
    $telegramId = location_telegram_id_from_init_data($initData);
    if ($telegramId <= 0) return ['ok'=>false,'error'=>'invalid_telegram_webapp','message'=>'Identitas Telegram Mini App tidak valid.'];
    if ($latitude < -90 || $latitude > 90 || $longitude < -180 || $longitude > 180) return ['ok'=>false,'error'=>'invalid_coordinates','message'=>'Koordinat tidak valid.'];
    if ($accuracy !== null && ($accuracy < 0 || $accuracy > 10000)) $accuracy = null;
    location_ensure_schema();
    $st = db()->prepare('SELECT id,name,nik,sto,is_active FROM technicians WHERE telegram_id=? LIMIT 1');
    $st->execute([$telegramId]);
    $tech = $st->fetch();
    if (!$tech || !(int)$tech['is_active']) return ['ok'=>false,'error'=>'technician_not_active','message'=>'Teknisi tidak aktif.'];
    $now = location_iso_now();
    db()->prepare('INSERT INTO technician_current_locations(technician_id,telegram_id,latitude,longitude,accuracy,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(technician_id) DO UPDATE SET telegram_id=excluded.telegram_id,latitude=excluded.latitude,longitude=excluded.longitude,accuracy=excluded.accuracy,updated_at=excluded.updated_at')->execute([(int)$tech['id'],$telegramId,$latitude,$longitude,$accuracy,$now]);
    db()->prepare('INSERT INTO technician_presence(technician_id,telegram_id,last_seen) VALUES(?,?,?) ON CONFLICT(technician_id) DO UPDATE SET telegram_id=excluded.telegram_id,last_seen=excluded.last_seen')->execute([(int)$tech['id'],$telegramId,$now]);
    return ['ok'=>true,'updated_at'=>$now,'technician'=>['id'=>(int)$tech['id'],'telegram_id'=>$telegramId,'name'=>$tech['name'],'nik'=>$tech['nik'],'sto'=>$tech['sto']],'location'=>['latitude'=>$latitude,'longitude'=>$longitude,'accuracy'=>$accuracy]];
}

function location_list_for_viewer(array $viewer): array {
    location_ensure_schema();
    $role = strtolower(trim((string)($viewer['role'] ?? '')));
    $st = db()->query('SELECT t.id AS technician_id,t.telegram_id,t.name,t.nik,t.sto,t.is_active,p.last_seen,l.latitude,l.longitude,l.accuracy,l.updated_at AS location_updated_at FROM technicians t LEFT JOIN technician_presence p ON p.technician_id=t.id LEFT JOIN technician_current_locations l ON l.technician_id=t.id WHERE t.is_active=1 ORDER BY COALESCE(p.last_seen,l.updated_at) DESC');
    $rows = [];
    $now = time();
    foreach ($st->fetchAll() as $row) {
        if ($role === 'technician' && (int)$row['technician_id'] !== (int)$viewer['id']) continue;
        $lastSeenTs = $row['last_seen'] ? (strtotime((string)$row['last_seen']) ?: 0) : 0;
        $locationTs = $row['location_updated_at'] ? (strtotime((string)$row['location_updated_at']) ?: 0) : 0;
        $presenceAge = $lastSeenTs > 0 ? max(0, $now - $lastSeenTs) : PHP_INT_MAX;
        $locationAge = $locationTs > 0 ? max(0, $now - $locationTs) : PHP_INT_MAX;
        $online = $presenceAge <= 120;
        $hasLocation = $locationTs > 0 && $locationAge <= 1800 && $row['latitude'] !== null && $row['longitude'] !== null;
        if (!$online && !$hasLocation) continue;
        $status = $online ? 'ONLINE' : ($locationAge <= 600 ? 'IDLE' : 'OFFLINE');
        $rows[] = [
            'technician_id'=>(int)$row['technician_id'],
            'telegram_id'=>(int)$row['telegram_id'],
            'name'=>$row['name'],'nik'=>$row['nik'],'sto'=>$row['sto'],
            'latitude'=>$hasLocation?(float)$row['latitude']:null,
            'longitude'=>$hasLocation?(float)$row['longitude']:null,
            'accuracy'=>$hasLocation&&$row['accuracy']!==null?(float)$row['accuracy']:null,
            'updated_at'=>$row['last_seen'] ?: $row['location_updated_at'],
            'age_seconds'=>$online?$presenceAge:($locationAge===PHP_INT_MAX?null:$locationAge),
            'status'=>$status,
            'online'=>$online,
            'gps_active'=>$hasLocation,
            'gps_age_seconds'=>$hasLocation?$locationAge:null,
        ];
    }
    return ['ok'=>true,'server_time'=>location_iso_now(),'count'=>count($rows),'locations'=>$rows];
}
