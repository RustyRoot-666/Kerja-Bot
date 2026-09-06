<?php

declare(strict_types=1);

require_once __DIR__ . '/../webapp/php_backend.php';
require_once __DIR__ . '/../webapp/php_area_success.php';

$limit=0;
foreach($argv as $arg)if(str_starts_with($arg,'--limit='))$limit=max(0,(int)substr($arg,8));

/*
 * IMPORTANT:
 * Geocoder ONLY receives a KECAMATAN query.
 * Customer addresses are never sent to the geocoder and never become map points.
 * The map has one point per kecamatan; customer/area data is drill-down data.
 */
function geocode_kecamatan(string $kecamatan): ?array {
    $queries=[
        'Kecamatan '.$kecamatan.', Kota Surabaya, Jawa Timur, Indonesia',
        $kecamatan.', Surabaya, Jawa Timur, Indonesia'
    ];
    foreach($queries as $i=>$query){
        $url='https://nominatim.openstreetmap.org/search?'.http_build_query([
            'q'=>$query,'format'=>'jsonv2','limit'=>1,'countrycodes'=>'id'
        ]);
        $ctx=stream_context_create(['http'=>[
            'timeout'=>15,
            'header'=>"User-Agent: Kerja-Bot/1.0 (area-success-kecamatan-map)\r\nAccept: application/json\r\n"
        ]]);
        $raw=@file_get_contents($url,false,$ctx);
        if($raw!==false){
            $items=json_decode($raw,true);
            if(is_array($items)&&!empty($items[0]['lat'])&&!empty($items[0]['lon']))return [
                'latitude'=>(float)$items[0]['lat'],
                'longitude'=>(float)$items[0]['lon'],
                'display_name'=>(string)($items[0]['display_name']??$query)
            ];
        }
        if($i<count($queries)-1)usleep(1100000);
    }
    return null;
}

$snapshot=area_success_snapshot();
if(!($snapshot['ok']??false)){fwrite(STDERR,"Gagal membaca snapshot Area Success.\n");exit(1);}

$kecs=$snapshot['areas'];
$pdo=db();
$pdo->exec("CREATE TABLE IF NOT EXISTS area_success_geocodes (
    area_key TEXT PRIMARY KEY,
    area_name TEXT NOT NULL,
    kelurahan TEXT,
    kecamatan TEXT,
    latitude REAL,
    longitude REAL,
    display_name TEXT,
    status TEXT NOT NULL DEFAULT 'failed',
    attempts INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT
)");
foreach(['kelurahan','kecamatan'] as $column){try{$pdo->exec("ALTER TABLE area_success_geocodes ADD COLUMN {$column} TEXT");}catch(Throwable $e){}}

$total=count($kecs);$checked=0;$done=0;$cached=0;$failed=0;
echo "AREA SUCCESS GEOCODER\n";
echo "Map level: KECAMATAN ONLY\n";
echo "Unique kecamatan: {$total}\n";
echo "Geocode strategy: KECAMATAN -> ONE MAP POINT\n";
echo "Customer addresses are NOT geocoded. They remain drill-down details.\n";

foreach($kecs as $k){
    if($limit>0&&$checked>=$limit)break;
    $checked++;
    $kec=strtoupper(trim((string)$k['name']));
    $key=strtolower($kec);
    $st=$pdo->prepare('SELECT status,latitude,longitude,display_name FROM area_success_geocodes WHERE area_key=? LIMIT 1');
    $st->execute([$key]);$existing=$st->fetch();
    if($existing&&$existing['status']==='ok'&&$existing['latitude']!==null&&$existing['longitude']!==null){
        $cached++;echo "CACHED {$checked}/{$total} {$kec} -> {$existing['latitude']},{$existing['longitude']}\n";continue;
    }
    $geo=geocode_kecamatan($kec);$now=date('Y-m-d H:i:s');
    if(!$geo){
        $pdo->prepare("INSERT INTO area_success_geocodes(area_key,area_name,kecamatan,status,attempts,updated_at) VALUES(?,?,?,'failed',1,?) ON CONFLICT(area_key) DO UPDATE SET area_name=excluded.area_name,kecamatan=excluded.kecamatan,status='failed',attempts=area_success_geocodes.attempts+1,updated_at=excluded.updated_at")
            ->execute([$key,$kec,$kec,$now]);
        $failed++;echo "FAIL {$checked}/{$total} {$kec}\n";continue;
    }
    $pdo->prepare("INSERT INTO area_success_geocodes(area_key,area_name,kecamatan,latitude,longitude,display_name,status,attempts,updated_at) VALUES(?,?,?,?,?,?, 'ok',1,?) ON CONFLICT(area_key) DO UPDATE SET area_name=excluded.area_name,kecamatan=excluded.kecamatan,latitude=excluded.latitude,longitude=excluded.longitude,display_name=excluded.display_name,status='ok',attempts=area_success_geocodes.attempts+1,updated_at=excluded.updated_at")
        ->execute([$key,$kec,$kec,$geo['latitude'],$geo['longitude'],$geo['display_name'],$now]);
    $done++;echo "OK {$checked}/{$total} {$kec} -> {$geo['latitude']},{$geo['longitude']}\n";usleep(1100000);
}

echo "DONE checked={$checked} kecamatan_geocoded={$done} cached={$cached} failed={$failed}\n";
