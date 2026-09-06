<?php

declare(strict_types=1);

require_once __DIR__ . '/../webapp/php_backend.php';
require_once __DIR__ . '/../webapp/php_area_success.php';

$limit = 0;
foreach ($argv as $arg) {
    if (str_starts_with($arg, '--limit=')) $limit = max(0, (int)substr($arg, 8));
}

function area_success_kecamatan(string $address): string {
    $s = area_success_normalize($address);
    if ($s === '') return '';
    $map = [
        'KEJAWAN PUTIH TAMBAK' => 'SUKOLILO',
        'KEPUTIH' => 'SUKOLILO', 'NGINDEN' => 'SUKOLILO', 'PUMPUNGAN' => 'SUKOLILO',
        'MENUR' => 'SUKOLILO', 'SEMOLOWARU' => 'SUKOLILO', 'SUKOLILO' => 'SUKOLILO',
        'MOJO' => 'GUBENG', 'AIRLANGGA' => 'GUBENG', 'GUBENG' => 'GUBENG',
        'KERTAJAYA' => 'GUBENG', 'TENGGILIS MEJOYO' => 'TENGGILIS MEJOYO',
        'GUNUNG ANYAR' => 'GUNUNG ANYAR', 'RUNGKUT' => 'RUNGKUT', 'MULYOREJO' => 'MULYOREJO',
        'TAMBAKSARI' => 'TAMBAKSARI', 'WONOCOLO' => 'WONOCOLO', 'WONOKROMO' => 'WONOKROMO',
        'WIYUNG' => 'WIYUNG', 'DUKUH PAKIS' => 'DUKUH PAKIS', 'LAKARSANTRI' => 'LAKARSANTRI',
        'SAMBIKEREP' => 'SAMBIKEREP', 'SUKOMANUNGGAL' => 'SUKOMANUNGGAL', 'TANDES' => 'TANDES',
        'ASEMROWO' => 'ASEMROWO', 'BENOWO' => 'BENOWO', 'BUBUTAN' => 'BUBUTAN', 'BULAK' => 'BULAK',
        'GAYUNGAN' => 'GAYUNGAN', 'GENTENG' => 'GENTENG', 'JAMBANGAN' => 'JAMBANGAN',
        'KARANG PILANG' => 'KARANG PILANG', 'KENJERAN' => 'KENJERAN', 'KREMBANGAN' => 'KREMBANGAN',
        'PABEAN CANTIAN' => 'PABEAN CANTIAN', 'PAKAL' => 'PAKAL', 'SAWAHAN' => 'SAWAHAN',
        'SEMAMPIR' => 'SEMAMPIR', 'SIMOKERTO' => 'SIMOKERTO', 'TEGALSARI' => 'TEGALSARI'
    ];
    uksort($map, static fn($a,$b) => strlen($b) <=> strlen($a));
    foreach ($map as $locality => $kecamatan) {
        if (preg_match('/(?:^|\s)' . preg_quote($locality, '/') . '(?:\s|$)/i', $s)) return $kecamatan;
    }
    return '';
}

function area_success_kelurahan(string $address): string {
    $s = area_success_normalize($address);
    $map = [
        'KEJAWAN PUTIH TAMBAK' => 'KEJAWAN PUTIH TAMBAK'
    ];
    foreach ($map as $kelurahan => $name) {
        if (preg_match('/(?:^|\s)' . preg_quote($kelurahan, '/') . '(?:\s|$)/i', $s)) return $name;
    }
    return '';
}

$rows = fetch_sheet(false);
$areas = [];
foreach ($rows as $row) {
    $address = trim((string)($row['address'] ?? ''));
    if ($address === '') continue;
    $area = area_success_locality($address);
    if ($area === '' || $area === 'LAINNYA') continue;
    $kecamatan = area_success_kecamatan($address);
    $kelurahan = area_success_kelurahan($address);
    $areas[$area] ??= ['kecamatan'=>$kecamatan, 'kelurahan'=>$kelurahan];
    if ($areas[$area]['kecamatan'] === '' && $kecamatan !== '') $areas[$area]['kecamatan'] = $kecamatan;
    if ($areas[$area]['kelurahan'] === '' && $kelurahan !== '') $areas[$area]['kelurahan'] = $kelurahan;
}
ksort($areas);

$pdo = db();
$pdo->exec("CREATE TABLE IF NOT EXISTS area_success_geocodes (
    area_key TEXT PRIMARY KEY, area_name TEXT NOT NULL, kecamatan TEXT, kelurahan TEXT,
    latitude REAL, longitude REAL, display_name TEXT, status TEXT NOT NULL DEFAULT 'failed',
    attempts INTEGER NOT NULL DEFAULT 0, updated_at TEXT
)");
foreach (['kecamatan','kelurahan'] as $column) {
    try { $pdo->exec("ALTER TABLE area_success_geocodes ADD COLUMN {$column} TEXT"); } catch (Throwable $e) {}
}

function geocode_area_request(string $area, string $kecamatan = '', string $kelurahan = ''): ?array {
    $parts = [$area];
    if ($kelurahan !== '' && stripos($area, $kelurahan) === false) $parts[] = $kelurahan;
    if ($kecamatan !== '' && stripos($area, $kecamatan) === false) $parts[] = $kecamatan;
    $parts[] = 'Surabaya'; $parts[] = 'Jawa Timur'; $parts[] = 'Indonesia';
    $query = implode(', ', $parts);
    $url = 'https://nominatim.openstreetmap.org/search?' . http_build_query(['q'=>$query,'format'=>'jsonv2','limit'=>1,'countrycodes'=>'id']);
    $ctx = stream_context_create(['http'=>['timeout'=>15,'header'=>"User-Agent: Kerja-Bot/1.0 (area-success-map)\r\nAccept: application/json\r\n"]]);
    $raw = @file_get_contents($url, false, $ctx);
    if ($raw === false) return null;
    $items = json_decode($raw, true);
    if (!is_array($items) || empty($items[0]['lat']) || empty($items[0]['lon'])) return null;
    return ['latitude'=>(float)$items[0]['lat'],'longitude'=>(float)$items[0]['lon'],'display_name'=>(string)($items[0]['display_name'] ?? $query)];
}

$total=count($areas); $checked=0; $done=0; $cached=0; $failed=0;
echo "AREA SUCCESS GEOCODER\nUnique customer areas: {$total}\nGeocode query: CUSTOMER AREA + KELURAHAN + KECAMATAN + SURABAYA\nKelurahan/kecamatan are context only; success remains per customer area.\n";
foreach (array_keys($areas) as $area) {
    if ($limit > 0 && $checked >= $limit) break;
    $checked++; $key=strtolower($area); $kecamatan=(string)$areas[$area]['kecamatan']; $kelurahan=(string)$areas[$area]['kelurahan'];
    $st=$pdo->prepare('SELECT status,latitude,longitude FROM area_success_geocodes WHERE area_key=? LIMIT 1'); $st->execute([$key]); $existing=$st->fetch();
    if ($existing && $existing['status']==='ok' && $existing['latitude']!==null && $existing['longitude']!==null) { $cached++; continue; }
    $geo=geocode_area_request($area,$kecamatan,$kelurahan); $now=date('Y-m-d H:i:s');
    if ($geo) {
        $pdo->prepare("INSERT INTO area_success_geocodes(area_key,area_name,kecamatan,kelurahan,latitude,longitude,display_name,status,attempts,updated_at) VALUES(?,?,?,?,?,?,?,'ok',1,?) ON CONFLICT(area_key) DO UPDATE SET area_name=excluded.area_name,kecamatan=excluded.kecamatan,kelurahan=excluded.kelurahan,latitude=excluded.latitude,longitude=excluded.longitude,display_name=excluded.display_name,status='ok',attempts=area_success_geocodes.attempts+1,updated_at=excluded.updated_at")->execute([$key,$area,$kecamatan,$kelurahan,$geo['latitude'],$geo['longitude'],$geo['display_name'],$now]);
        $done++; echo "OK {$checked}/{$total} {$area} [{$kelurahan} / {$kecamatan}] -> {$geo['latitude']},{$geo['longitude']}\n";
    } else {
        $pdo->prepare("INSERT INTO area_success_geocodes(area_key,area_name,kecamatan,kelurahan,status,attempts,updated_at) VALUES(?,?,?,?,'failed',1,?) ON CONFLICT(area_key) DO UPDATE SET area_name=excluded.area_name,kecamatan=excluded.kecamatan,kelurahan=excluded.kelurahan,status='failed',attempts=area_success_geocodes.attempts+1,updated_at=excluded.updated_at")->execute([$key,$area,$kecamatan,$kelurahan,$now]);
        $failed++; echo "FAIL {$checked}/{$total} {$area} [{$kelurahan} / {$kecamatan}]\n";
    }
    usleep(1100000);
}
echo "DONE checked={$checked} geocoded={$done} cached={$cached} failed={$failed}\n";
