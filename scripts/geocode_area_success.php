<?php

declare(strict_types=1);

require_once __DIR__ . '/../webapp/php_backend.php';
require_once __DIR__ . '/../webapp/php_area_success.php';

$limit = 0;
foreach ($argv as $arg) if (str_starts_with($arg, '--limit=')) $limit = max(0, (int)substr($arg, 8));

function area_success_location_context(string $address): array {
    $s = area_success_normalize($address);
    if ($s === '') return ['kelurahan'=>'', 'kecamatan'=>''];
    $map = [
        'KEJAWAN PUTIH TAMBAK'=>'MULYOREJO','KEJAWAN PUTIH MUTIARA'=>'MULYOREJO',
        'MEDOKAN SEMAMPIR'=>'SUKOLILO','KALISARI'=>'MULYOREJO',
        'NGINDEN JANGKUNGAN'=>'SUKOLILO','MENUR PUMPUNGAN'=>'SUKOLILO','KEPUTIH'=>'SUKOLILO','NGINDEN'=>'SUKOLILO','PUMPUNGAN'=>'SUKOLILO','SEMOLOWARU'=>'SUKOLILO',
        'KERTAJAYA'=>'GUBENG','MOJO'=>'GUBENG','AIRLANGGA'=>'GUBENG','GUBENG'=>'GUBENG','MULYOREJO'=>'MULYOREJO',
        'TENGGILIS MEJOYO'=>'TENGGILIS MEJOYO','GUNUNG ANYAR'=>'GUNUNG ANYAR','RUNGKUT'=>'RUNGKUT','TAMBAKSARI'=>'TAMBAKSARI','WONOCOLO'=>'WONOCOLO','WONOKROMO'=>'WONOKROMO',
        'WIYUNG'=>'WIYUNG','DUKUH PAKIS'=>'DUKUH PAKIS','LAKARSANTRI'=>'LAKARSANTRI','SAMBIKEREP'=>'SAMBIKEREP','SUKOLILO'=>'SUKOLILO','SUKOMANUNGGAL'=>'SUKOMANUNGGAL',
        'TANDES'=>'TANDES','ASEMROWO'=>'ASEMROWO','BENOWO'=>'BENOWO','BUBUTAN'=>'BUBUTAN','BULAK'=>'BULAK','GAYUNGAN'=>'GAYUNGAN','GENTENG'=>'GENTENG',
        'JAMBANGAN'=>'JAMBANGAN','KARANG PILANG'=>'KARANG PILANG','KENJERAN'=>'KENJERAN','KREMBANGAN'=>'KREMBANGAN','PABEAN CANTIAN'=>'PABEAN CANTIAN',
        'PAKAL'=>'PAKAL','SAWAHAN'=>'SAWAHAN','SEMAMPIR'=>'SEMAMPIR','SIMOKERTO'=>'SIMOKERTO','TEGALSARI'=>'TEGALSARI'
    ];
    uksort($map, static fn($a,$b)=>strlen($b)<=>strlen($a));
    foreach ($map as $kel=>$kec) if (preg_match('/(?:^|\s)'.preg_quote($kel,'/').'(?=\s|$)/i',$s)) return ['kelurahan'=>$kel,'kecamatan'=>$kec];
    return ['kelurahan'=>'','kecamatan'=>''];
}

function area_success_area_context(string $area): array {
    $known = [
        'APARTEMEN BALE HINGGIL'=>['MEDOKAN SEMAMPIR','SUKOLILO'],
        'APARTEMEN EDUCITY'=>['KEJAWAN PUTIH TAMBAK','MULYOREJO'],
        'APARTEMEN ONE GALAXY'=>['MULYOREJO','MULYOREJO'],
        'APARTEMEN PUNCAK KERTAJAYA'=>['KERTAJAYA','GUBENG'],
        'APARTEMEN DIAN REGENCY'=>['KEPUTIH','SUKOLILO'],
        'BASKARA'=>['KALISARI','MULYOREJO'],'BASKARA SARI'=>['KALISARI','MULYOREJO'],'BASKARA SAWAH'=>['KALISARI','MULYOREJO'],
        'BASKARA SELATAN'=>['KALISARI','MULYOREJO'],'BASKARA TENGAH'=>['KALISARI','MULYOREJO'],'BASKARA UTARA'=>['KALISARI','MULYOREJO']
    ];
    $v=$known[strtoupper(trim($area))] ?? ['', ''];
    return ['kelurahan'=>$v[0],'kecamatan'=>$v[1]];
}

$rows=fetch_sheet(false); $areas=[];
foreach ($rows as $row) {
    $address=trim((string)($row['address']??'')); if($address==='') continue;
    $area=area_success_locality($address); if($area===''||$area==='LAINNYA') continue;
    $ctx=area_success_location_context($address); $known=area_success_area_context($area); if($known['kecamatan']!=='') $ctx=$known;
    $areas[$area] ??= ['kelurahan'=>$ctx['kelurahan'],'kecamatan'=>$ctx['kecamatan'],'addresses'=>[]];
    if($ctx['kelurahan']!==''){ $areas[$area]['kelurahan']=$ctx['kelurahan']; $areas[$area]['kecamatan']=$ctx['kecamatan']; }
    if(!in_array($address,$areas[$area]['addresses'],true)) $areas[$area]['addresses'][]=$address;
}
ksort($areas);

$pdo=db();
$pdo->exec("CREATE TABLE IF NOT EXISTS area_success_geocodes (area_key TEXT PRIMARY KEY,area_name TEXT NOT NULL,kelurahan TEXT,kecamatan TEXT,latitude REAL,longitude REAL,display_name TEXT,status TEXT NOT NULL DEFAULT 'failed',attempts INTEGER NOT NULL DEFAULT 0,updated_at TEXT)");
foreach(['kelurahan','kecamatan'] as $column){try{$pdo->exec("ALTER TABLE area_success_geocodes ADD COLUMN {$column} TEXT");}catch(Throwable $e){}}

function geocode_http(string $query): ?array {
    $url='https://nominatim.openstreetmap.org/search?'.http_build_query(['q'=>$query,'format'=>'jsonv2','limit'=>1,'countrycodes'=>'id']);
    $ctx=stream_context_create(['http'=>['timeout'=>15,'header'=>"User-Agent: Kerja-Bot/1.0 (area-success-map)\r\nAccept: application/json\r\n"]]);
    $raw=@file_get_contents($url,false,$ctx); if($raw===false)return null;
    $items=json_decode($raw,true); if(!is_array($items)||empty($items[0]['lat'])||empty($items[0]['lon']))return null;
    return ['latitude'=>(float)$items[0]['lat'],'longitude'=>(float)$items[0]['lon'],'display_name'=>(string)($items[0]['display_name']??$query)];
}

function geocode_area_candidates(string $area,string $kelurahan,string $kecamatan,array $addresses): ?array {
    $queries=[];
    $queries[]=implode(', ',array_filter([$area,$kecamatan,'Surabaya','Jawa Timur','Indonesia']));
    $queries[]=implode(', ',array_filter([$area,'Surabaya','Jawa Timur','Indonesia']));
    foreach(array_slice($addresses,0,3) as $address) $queries[]=implode(', ',array_filter([trim($address),$kecamatan,'Surabaya','Jawa Timur','Indonesia']));
    $points=[];$names=[];
    foreach(array_values(array_unique($queries)) as $query){
        $geo=geocode_http($query);
        if($geo){$points[]=[$geo['latitude'],$geo['longitude']];$names[]=$geo['display_name'];if(count($points)>=3)break;}
        usleep(1100000);
    }
    if(!$points)return null;
    return ['latitude'=>array_sum(array_column($points,0))/count($points),'longitude'=>array_sum(array_column($points,1))/count($points),'display_name'=>$names[0],'coordinate_count'=>count($points)];
}

$total=count($areas);$checked=0;$done=0;$cached=0;$failed=0;
echo "AREA SUCCESS GEOCODER\nUnique customer areas: {$total}\nGeocode strategy: AREA + KECAMATAN -> AREA + SURABAYA -> REAL CUSTOMER ADDRESS\nKelurahan is metadata only; success remains per customer area.\n";
foreach($areas as $area=>$info){
    if($limit>0&&$checked>=$limit)break; $checked++; $key=strtolower($area);
    $kel=(string)($info['kelurahan']??'');$kec=(string)($info['kecamatan']??'');$addresses=(array)($info['addresses']??[]);
    $st=$pdo->prepare('SELECT status,latitude,longitude FROM area_success_geocodes WHERE area_key=? LIMIT 1');$st->execute([$key]);$existing=$st->fetch();
    if($existing&&$existing['status']==='ok'&&$existing['latitude']!==null&&$existing['longitude']!==null){$cached++;continue;}
    $geo=geocode_area_candidates($area,$kel,$kec,$addresses);$now=date('Y-m-d H:i:s');
    if($geo){
        $pdo->prepare("INSERT INTO area_success_geocodes(area_key,area_name,kelurahan,kecamatan,latitude,longitude,display_name,status,attempts,updated_at) VALUES(?,?,?,?,?,?,?,'ok',1,?) ON CONFLICT(area_key) DO UPDATE SET area_name=excluded.area_name,kelurahan=excluded.kelurahan,kecamatan=excluded.kecamatan,latitude=excluded.latitude,longitude=excluded.longitude,display_name=excluded.display_name,status='ok',attempts=area_success_geocodes.attempts+1,updated_at=excluded.updated_at")->execute([$key,$area,$kel,$kec,$geo['latitude'],$geo['longitude'],$geo['display_name'],$now]);
        $done++;echo "OK {$checked}/{$total} {$area} [{$kel} | {$kec}] -> {$geo['latitude']},{$geo['longitude']} (points={$geo['coordinate_count']})\n";
    }else{
        $pdo->prepare("INSERT INTO area_success_geocodes(area_key,area_name,kelurahan,kecamatan,status,attempts,updated_at) VALUES(?,?,?,?, 'failed',1,?) ON CONFLICT(area_key) DO UPDATE SET area_name=excluded.area_name,kelurahan=excluded.kelurahan,kecamatan=excluded.kecamatan,status='failed',attempts=area_success_geocodes.attempts+1,updated_at=excluded.updated_at")->execute([$key,$area,$kel,$kec,$now]);
        $failed++;echo "FAIL {$checked}/{$total} {$area} [{$kel} | {$kec}]\n";
    }
    usleep(1100000);
}
echo "DONE checked={$checked} geocoded={$done} cached={$cached} failed={$failed}\n";
