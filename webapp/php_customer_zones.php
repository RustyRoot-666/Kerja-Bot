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

function customer_zone_roman(int $n): string {
    static $roman = ['', 'I','II','III','IV','V','VI','VII','VIII','IX','X','XI','XII','XIII','XIV','XV','XVI','XVII','XVIII','XIX','XX'];
    return ($n >= 1 && $n <= 20) ? $roman[$n] : (string)$n;
}

function customer_zone_normalize_street(string $address): string {
    $text = strtoupper(trim($address));
    $text = preg_replace('/[^A-Z0-9\/ -]+/u', ' ', $text) ?: '';
    $text = preg_replace('/\s+/', ' ', $text) ?: '';
    $text = trim(str_replace(['JLN ', 'JALAN '], ['JL ', 'JL '], $text));
    $text = preg_replace('/\bGANG\b/', 'GG', $text) ?: $text;
    if ($text === '') return '';
    $parts = preg_split('/\s+/', $text) ?: [];
    $numeric = [];
    foreach ($parts as $i => $part) if (preg_match('/^\d+$/', $part)) $numeric[] = $i;
    if (count($numeric) >= 2) {
        $houseIndex = $numeric[count($numeric)-1];
        foreach (array_slice($numeric, 0, -1) as $i) $parts[$i] = customer_zone_roman((int)$parts[$i]);
        $parts = array_slice($parts, 0, $houseIndex);
        return trim(implode(' ', $parts));
    }
    if (count($numeric) === 1) {
        $i = $numeric[0];
        if ($i > 0) return trim(implode(' ', array_slice($parts, 0, $i)));
    }
    return trim(implode(' ', $parts));
}

function customer_zone_key(string $address): string {
    $street = customer_zone_normalize_street($address);
    $s = preg_replace('/\s+/u', ' ', trim($street)) ?: '';
    return strtolower($s);
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

function customer_zone_sync(int $limit=8): array {
    customer_zone_ensure_schema();
    require_once __DIR__.'/php_orderanku_fix.php';
    $refs = orderanku_fetch_sheet(false);
    $pdo = db();
    $streets = [];
    foreach ($refs as $row) {
        if (orderanku_sheet_bucket($row) === 'close') continue;
        $address = trim((string)($row['address'] ?? ''));
        $street = customer_zone_normalize_street($address);
        if ($street !== '') $streets[customer_zone_key($street)] = $street;
    }
    $done = 0; $failed = 0; $checked = 0;
    foreach ($streets as $key => $street) {
        if ($checked >= $limit) break;
        $st = $pdo->prepare('SELECT status FROM customer_geocodes WHERE address_key=? LIMIT 1');
        $st->execute([$key]);
        $existing = $st->fetchColumn();
        if ($existing === 'ok') continue;
        $checked++;
        $geo = customer_zone_geocode($street);
        $now = date('Y-m-d H:i:s');
        if ($geo) {
            $pdo->prepare("INSERT INTO customer_geocodes(address_key,address,latitude,longitude,display_name,status,attempts,updated_at) VALUES(?,?,?,?,?,'ok',1,?) ON CONFLICT(address_key) DO UPDATE SET address=excluded.address,latitude=excluded.latitude,longitude=excluded.longitude,display_name=excluded.display_name,status='ok',attempts=customer_geocodes.attempts+1,updated_at=excluded.updated_at")
                ->execute([$key,$street,$geo['latitude'],$geo['longitude'],$geo['display_name'],$now]);
            $done++;
        } else {
            $pdo->prepare("INSERT INTO customer_geocodes(address_key,address,status,attempts,updated_at) VALUES(?,?, 'failed',1,?) ON CONFLICT(address_key) DO UPDATE SET address=excluded.address,status='failed',attempts=customer_geocodes.attempts+1,updated_at=excluded.updated_at")
                ->execute([$key,$street,$now]);
            $failed++;
        }
        usleep(1100000);
    }
    return ['geocoded'=>$done,'failed'=>$failed,'streets'=>count($streets),'checked'=>$checked];
}

function customer_zone_snapshot(bool $sync=false): array {
    customer_zone_ensure_schema();
    if ($sync) customer_zone_sync(8);
    require_once __DIR__.'/php_orderanku_fix.php';
    $refs = orderanku_fetch_sheet(false);
    $geoRows = db()->query("SELECT address_key,address,latitude,longitude,display_name,status FROM customer_geocodes WHERE status='ok'")->fetchAll();
    $geo = [];
    foreach ($geoRows as $g) $geo[(string)$g['address_key']] = $g;
    $zones = [];
    $customers = [];
    foreach ($refs as $row) {
        if (orderanku_sheet_bucket($row) === 'close') continue;
        $address = trim((string)($row['address'] ?? ''));
        $street = customer_zone_normalize_street($address);
        if ($street === '') continue;
        $key = customer_zone_key($street);
        if (!isset($geo[$key])) continue;
        $g = $geo[$key];
        $lat=(float)$g['latitude']; $lng=(float)$g['longitude'];
        if (!isset($zones[$key])) $zones[$key]=['zone_id'=>'Z'.str_pad((string)(count($zones)+1),2,'0',STR_PAD_LEFT),'street'=>$street,'latitude'=>$lat,'longitude'=>$lng,'total'=>0,'open'=>0,'close'=>0,'update'=>0,'menolak'=>0,'orders'=>[]];
        $z =& $zones[$key];
        $z['total']++;
        $bucket=orderanku_sheet_bucket($row);
        if ($bucket==='open') $z['open']++; elseif ($bucket==='close') $z['close']++; elseif ($bucket==='update') $z['update']++;
        $status=norm($row['status']??''); if (in_array($status,['MENOLAK','REJECT','DITOLAK'],true)) $z['menolak']++;
        $z['orders'][]=['customer_name'=>$row['customer_name'] ?? '','service_number'=>$row['service_number'] ?? '','ticket_id'=>$row['ticket_id'] ?? '','address'=>$address,'sto'=>$row['sto'] ?? '','status'=>$row['status'] ?? '','result'=>$row['status'] ?? '','customer_phone'=>$row['customer_phone'] ?? '','ont_type'=>$row['ont_type'] ?? '','valins_id'=>$row['valins_id'] ?? ''];
        $customers[]=['customer_name'=>$row['customer_name'] ?? '','service_number'=>$row['service_number'] ?? '','ticket_id'=>$row['ticket_id'] ?? '','address'=>$address,'latitude'=>$lat,'longitude'=>$lng,'zone_id'=>$z['zone_id'],'street'=>$street];
        unset($z);
    }
    foreach ($zones as &$z) {
        $z['label']=$z['street'];
        $z['orders']=array_slice($z['orders'],0,50);
    }
    unset($z);
    return ['ok'=>true,'server_time'=>date('Y-m-d H:i:s'),'zones'=>array_values($zones),'customers'=>$customers,'geocoded_count'=>count($geoRows),'pending_estimate'=>max(0,count($refs)-count($geoRows))];
}
