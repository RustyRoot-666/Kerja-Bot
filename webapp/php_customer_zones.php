<?php

declare(strict_types=1);

function customer_zone_ensure_schema(): void {
    $pdo = db();
    $pdo->exec("CREATE TABLE IF NOT EXISTS customer_geocodes (
        address_key TEXT PRIMARY KEY,
        address TEXT NOT NULL,
        latitude REAL,
        longitude REAL,
        display_name TEXT,
        status TEXT NOT NULL DEFAULT 'pending',
        attempts INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL
    )");
    $pdo->exec('CREATE INDEX IF NOT EXISTS idx_customer_geocodes_status ON customer_geocodes(status)');
}

function customer_zone_key(string $address): string {
    $s = preg_replace('/\s+/u', ' ', trim($address));
    return strtolower((string)$s);
}

function customer_zone_geocode(string $address): ?array {
    $query = trim($address);
    if ($query === '') return null;
    $url = 'https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&countrycodes=id&q=' . rawurlencode($query . ', Surabaya, Jawa Timur, Indonesia');
    $ctx = stream_context_create(['http'=>[
        'timeout'=>12,
        'ignore_errors'=>true,
        'header'=>"User-Agent: Kerja-Bot/1.0 (customer-zone-map)\r\nAccept: application/json\r\n"
    ]]);
    $raw = @file_get_contents($url, false, $ctx);
    if ($raw === false) return null;
    $data = json_decode($raw, true);
    if (!is_array($data) || !$data) return null;
    $lat = isset($data[0]['lat']) ? (float)$data[0]['lat'] : null;
    $lng = isset($data[0]['lon']) ? (float)$data[0]['lon'] : null;
    if ($lat === null || $lng === null || !is_finite($lat) || !is_finite($lng)) return null;
    return ['latitude'=>$lat,'longitude'=>$lng,'display_name'=>(string)($data[0]['display_name'] ?? '')];
}

function customer_zone_sync(int $limit=3): array {
    customer_zone_ensure_schema();
    require_once __DIR__.'/php_orderanku_fix.php';
    $refs = orderanku_fetch_sheet(false);
    $pdo = db();
    $done = 0;
    $failed = 0;
    foreach ($refs as $row) {
        if (orderanku_sheet_bucket($row) === 'close') continue;
        $address = trim((string)($row['address'] ?? ''));
        if ($address === '') continue;
        $key = customer_zone_key($address);
        $st = $pdo->prepare('SELECT status FROM customer_geocodes WHERE address_key=? LIMIT 1');
        $st->execute([$key]);
        $existing = $st->fetchColumn();
        if ($existing === 'ok') continue;
        if ($done >= $limit) break;
        $geo = customer_zone_geocode($address);
        $now = date('Y-m-d H:i:s');
        if ($geo) {
            $pdo->prepare('INSERT INTO customer_geocodes(address_key,address,latitude,longitude,display_name,status,attempts,updated_at) VALUES(?,?,?,?,?,\'ok\',1,?) ON CONFLICT(address_key) DO UPDATE SET latitude=excluded.latitude,longitude=excluded.longitude,display_name=excluded.display_name,status=\'ok\',attempts=customer_geocodes.attempts+1,updated_at=excluded.updated_at')
                ->execute([$key,$address,$geo['latitude'],$geo['longitude'],$geo['display_name'],$now]);
            $done++;
        } else {
            $pdo->prepare('INSERT INTO customer_geocodes(address_key,address,status,attempts,updated_at) VALUES(?,?,\'failed\',1,?) ON CONFLICT(address_key) DO UPDATE SET status=\'failed\',attempts=customer_geocodes.attempts+1,updated_at=excluded.updated_at')
                ->execute([$key,$address,$now]);
            $failed++;
        }
        usleep(1100000);
    }
    return ['geocoded'=>$done,'failed'=>$failed];
}

function customer_zone_snapshot(bool $sync=false): array {
    customer_zone_ensure_schema();
    if ($sync) customer_zone_sync(3);
    require_once __DIR__.'/php_orderanku_fix.php';
    $refs = orderanku_fetch_sheet(false);
    $geoRows = db()->query("SELECT address_key,address,latitude,longitude,display_name,status FROM customer_geocodes WHERE status='ok'")->fetchAll();
    $geo = [];
    foreach ($geoRows as $g) $geo[$g['address_key']] = $g;
    $zones = [];
    $customers = [];
    foreach ($refs as $row) {
        if (orderanku_sheet_bucket($row) === 'close') continue;
        $address = trim((string)($row['address'] ?? ''));
        if ($address === '') continue;
        $key = customer_zone_key($address);
        if (!isset($geo[$key])) continue;
        $g = $geo[$key];
        $lat=(float)$g['latitude']; $lng=(float)$g['longitude'];
        // ~110m latitude cells; longitude cell is ~100m around Surabaya.
        $cellLat = floor($lat / 0.001) * 0.001;
        $cellLng = floor($lng / 0.001) * 0.001;
        $zoneKey = number_format($cellLat,3,'.','').',' . number_format($cellLng,3,'.','');
        if (!isset($zones[$zoneKey])) $zones[$zoneKey]=['zone_id'=>'Z'.str_pad((string)(count($zones)+1),2,'0',STR_PAD_LEFT),'latitude'=>0,'longitude'=>0,'total'=>0,'open'=>0,'orders'=>[]];
        $zones[$zoneKey]['latitude'] += $lat;
        $zones[$zoneKey]['longitude'] += $lng;
        $zones[$zoneKey]['total']++;
        $zones[$zoneKey]['open']++;
        $zones[$zoneKey]['orders'][]=['customer_name'=>$row['customer_name'] ?? '','service_number'=>$row['service_number'] ?? '','ticket_id'=>$row['ticket_id'] ?? '','address'=>$address,'sto'=>$row['sto'] ?? ''];
        $customers[]=['customer_name'=>$row['customer_name'] ?? '','service_number'=>$row['service_number'] ?? '','ticket_id'=>$row['ticket_id'] ?? '','address'=>$address,'latitude'=>$lat,'longitude'=>$lng,'zone_id'=>$zones[$zoneKey]['zone_id']];
    }
    foreach ($zones as &$z) {
        $z['latitude'] /= max(1,$z['total']);
        $z['longitude'] /= max(1,$z['total']);
        $z['label']='ZONE '.$z['zone_id'];
        $z['orders']=array_slice($z['orders'],0,20);
    }
    unset($z);
    return ['ok'=>true,'server_time'=>date('Y-m-d H:i:s'),'zones'=>array_values($zones),'customers'=>$customers,'geocoded_count'=>count($geoRows),'pending_estimate'=>max(0,count($refs)-count($geoRows))];
}
