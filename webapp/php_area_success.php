<?php

declare(strict_types=1);

/*
 * AREA SUCCESS MAP
 *
 * Level 1 = KECAMATAN only.
 * A map point represents one Surabaya kecamatan, never a street/area.
 * Customer area + full address are kept as drill-down data after the
 * kecamatan point is clicked.
 */
function area_success_normalize(string $address): string {
    $s = normalize_address($address);
    $s = preg_replace('/\b(?:SBY|SURABAYA|JAWA TIMUR|INDONESIA)\b.*$/', '', $s) ?: $s;
    return trim(preg_replace('/\s+/', ' ', $s) ?: '');
}

function area_success_color(float $rate): string {
    if ($rate < 25) return '#ef4444';
    if ($rate < 50) return '#f97316';
    if ($rate < 75) return '#eab308';
    return '#22c55e';
}

function area_success_admin_map(): array {
    return [
        'DUKUH KUPANG'=>'DUKUH PAKIS','DUKUH PAKIS'=>'DUKUH PAKIS','GUNUNG SARI'=>'DUKUH PAKIS','PRADAH KALIKENDAL'=>'DUKUH PAKIS',
        'DUKUH MENANGGAL'=>'GAYUNGAN','GAYUNGAN'=>'GAYUNGAN','KETINTANG'=>'GAYUNGAN','MENANGGAL'=>'GAYUNGAN',
        'JAMBANGAN'=>'JAMBANGAN','KARAH'=>'JAMBANGAN','KEBONSARI'=>'JAMBANGAN','PAGESANGAN'=>'JAMBANGAN',
        'KARANG PILANG'=>'KARANG PILANG','KEBRAON'=>'KARANG PILANG','KEDURUS'=>'KARANG PILANG','WARU GUNUNG'=>'KARANG PILANG',
        'BANYU URIP'=>'SAWAHAN','KUPANG KRAJAN'=>'SAWAHAN','PAKIS'=>'SAWAHAN','PETEMON'=>'SAWAHAN','PUTAT JAYA'=>'SAWAHAN','SAWAHAN'=>'SAWAHAN',
        'BABATAN'=>'WIYUNG','BALAS KLUMPRIK'=>'WIYUNG','JAJAR TUNGGAL'=>'WIYUNG','WIYUNG'=>'WIYUNG',
        'BENDUL MERISI'=>'WONOCOLO','JEMUR WONOSARI'=>'WONOCOLO','MARGOREJO'=>'WONOCOLO','SIDOSERMO'=>'WONOCOLO','SIWALANKERTO'=>'WONOCOLO',
        'DARMO'=>'WONOKROMO','JAGIR'=>'WONOKROMO','NGAGEL'=>'WONOKROMO','NGAGEL REJO'=>'WONOKROMO','SAWUNGGALING'=>'WONOKROMO','WONOKROMO'=>'WONOKROMO',
        'AIRLANGGA'=>'GUBENG','BARATAJAYA'=>'GUBENG','GUBENG'=>'GUBENG','KERTAJAYA'=>'GUBENG','MOJO'=>'GUBENG','PUCANG SEWU'=>'GUBENG',
        'GUNUNG ANYAR'=>'GUNUNG ANYAR','GUNUNG ANYAR TAMBAK'=>'GUNUNG ANYAR','RUNGKUT MENANGGAL'=>'GUNUNG ANYAR','RUNGKUT TENGAH'=>'GUNUNG ANYAR',
        'DUKUH SUTOREJO'=>'MULYOREJO','KALIJUDAN'=>'MULYOREJO','KALISARI'=>'MULYOREJO','KEJAWAN PUTIH TAMBAK'=>'MULYOREJO','MANYAR SABRANGAN'=>'MULYOREJO','MULYOREJO'=>'MULYOREJO',
        'KALIRUNGKUT'=>'RUNGKUT','KEDUNG BARUK'=>'RUNGKUT','MEDOKAN AYU'=>'RUNGKUT','PENJARINGANSARI'=>'RUNGKUT','RUNGKUT KIDUL'=>'RUNGKUT','WONOREJO'=>'RUNGKUT',
        'GEBANG PUTIH'=>'SUKOLILO','KEPUTIH'=>'SUKOLILO','KLAMPIS NGASEM'=>'SUKOLILO','MEDOKAN SEMAMPIR'=>'SUKOLILO','MENUR PUMPUNGAN'=>'SUKOLILO','NGINDEN JANGKUNGAN'=>'SUKOLILO','SEMOLOWARU'=>'SUKOLILO',
        'DUKUH SETRO'=>'TAMBAKSARI','GADING'=>'TAMBAKSARI','KAPASMADYA BARU'=>'TAMBAKSARI','PACARKELING'=>'TAMBAKSARI','PACARKEMBANG'=>'TAMBAKSARI','PLOSO'=>'TAMBAKSARI','RANGKAH'=>'TAMBAKSARI','TAMBAKSARI'=>'TAMBAKSARI',
        'KENDANGSARI'=>'TENGGILIS MEJOYO','KUTISARI'=>'TENGGILIS MEJOYO','PANJANG JIWO'=>'TENGGILIS MEJOYO','TENGGILIS MEJOYO'=>'TENGGILIS MEJOYO',
        'ASEM ROWO'=>'ASEM ROWO','ASEMROWO'=>'ASEM ROWO','GENTING KALIANAK'=>'ASEM ROWO','TAMBAK SARIOSO'=>'ASEM ROWO',
        'KANDANGAN'=>'BENOWO','ROMOKALISARI'=>'BENOWO','SEMEMI'=>'BENOWO','TAMBAK OSO WILANGUN'=>'BENOWO',
        'BANGKINGAN'=>'LAKARSANTRI','JERUK'=>'LAKARSANTRI','LAKARSANTRI'=>'LAKARSANTRI','LIDAH KULON'=>'LAKARSANTRI','LIDAH WETAN'=>'LAKARSANTRI','SUMURWELUT'=>'LAKARSANTRI',
        'BABAT JERAWAT'=>'PAKAL','BENOWO'=>'PAKAL','PAKAL'=>'PAKAL','SUMBER REJO'=>'PAKAL',
        'BERINGIN'=>'SAMBIKEREP','LONTAR'=>'SAMBIKEREP','MADE'=>'SAMBIKEREP','SAMBIKEREP'=>'SAMBIKEREP',
        'PUTAT GEDE'=>'SUKOMANUNGGAL','SIMOMULYO'=>'SUKOMANUNGGAL','SIMOMULYO BARU'=>'SUKOMANUNGGAL','SONOKWIJENAN'=>'SUKOMANUNGGAL','SUKOMANUNGGAL'=>'SUKOMANUNGGAL','TANJUNGSARI'=>'SUKOMANUNGGAL',
        'BALONGSARI'=>'TANDES','BANJAR SUGIHAN'=>'TANDES','KARANG POH'=>'TANDES','MANUKAN KULON'=>'TANDES','MANUKAN WETAN'=>'TANDES','TANDES'=>'TANDES',
        'ALUN ALUN CONTONG'=>'BUBUTAN','BUBUTAN'=>'BUBUTAN','GUNDIH'=>'BUBUTAN','JEPARA'=>'BUBUTAN','TEMBOK DUKUH'=>'BUBUTAN',
        'EMBONG KALIASIN'=>'GENTENG','GENTENG'=>'GENTENG','KAPASARI'=>'GENTENG','KETABANG'=>'GENTENG','PENELEH'=>'GENTENG',
        'KAPASAN'=>'SIMOKERTO','SIDODADI'=>'SIMOKERTO','SIMOKERTO'=>'SIMOKERTO','SIMOLAWANG'=>'SIMOKERTO','TAMBAKREJO'=>'SIMOKERTO',
        'DR SOETOMO'=>'TEGALSARI','DR SOETOMO'=>'TEGALSARI','KEDUNGDORO'=>'TEGALSARI','KEPUTRAN'=>'TEGALSARI','TEGALSARI'=>'TEGALSARI',
        'BULAK'=>'BULAK','KEDUNG COWEK'=>'BULAK','KENJERAN'=>'BULAK','SUKOLILO BARU'=>'BULAK',
        'BULAK BANTENG'=>'KENJERAN','SIDOTOPO WETAN'=>'KENJERAN','TAMBAK WEDI'=>'KENJERAN','TANAH KALI KEDINDING'=>'KENJERAN',
        'DUPAK'=>'KREMBANGAN','KEMAYORAN'=>'KREMBANGAN','KREMBANGAN SELATAN'=>'KREMBANGAN','MOROKREMBANGAN'=>'KREMBANGAN','PERAK BARAT'=>'KREMBANGAN',
        'BONGKARAN'=>'PABEAN CANTIAN','KREMBANGAN UTARA'=>'PABEAN CANTIAN','NYAMPLUNGAN'=>'PABEAN CANTIAN','TANJUNG PERAK'=>'PABEAN CANTIAN',
        'AMPEL'=>'SEMAMPIR','PEGIRIAN'=>'SEMAMPIR','SIDOTOPO'=>'SEMAMPIR','UJUNG'=>'SEMAMPIR','WONOKUSUMO'=>'SEMAMPIR'
    ];
    uksort($map, static fn($a,$b)=>strlen($b)<=>strlen($a));
    return $map;
}

function area_success_area_context(string $area): array {
    $known = [
        'APARTEMEN BALE HINGGIL'=>['MEDOKAN SEMAMPIR','SUKOLILO'],
        'APARTEMEN EDUCITY'=>['KEJAWAN PUTIH TAMBAK','MULYOREJO'],
        'APARTEMEN ONE GALAXY'=>['MULYOREJO','MULYOREJO'],
        'APARTEMEN PUNCAK KERTAJAYA'=>['KERTAJAYA','GUBENG'],
        'APARTEMEN DIAN REGENCY'=>['KEPUTIH','SUKOLILO'],
        'BASKARA'=>['KALISARI','MULYOREJO'],'BASKARA SARI'=>['KALISARI','MULYOREJO'],
        'BASKARA SAWAH'=>['KALISARI','MULYOREJO'],'BASKARA SELATAN'=>['KALISARI','MULYOREJO'],
        'BASKARA TENGAH'=>['KALISARI','MULYOREJO'],'BASKARA UTARA'=>['KALISARI','MULYOREJO']
    ];
    $v=$known[strtoupper(trim($area))]??['',''];
    return ['kelurahan'=>$v[0],'kecamatan'=>$v[1]];
}

function area_success_context(string $address, string $area=''): array {
    $s=area_success_normalize($address);
    $known=area_success_area_context($area);
    if ($known['kecamatan']!=='') return $known;
    foreach(area_success_admin_map() as $kel=>$kec){
        if(preg_match('/(?:^|\s)'.preg_quote($kel,'/').'(?=\s|$)/i',$s)) return ['kelurahan'=>$kel,'kecamatan'=>$kec];
    }
    return ['kelurahan'=>'','kecamatan'=>''];
}

function area_success_geocode_cached(string $kecamatan): ?array {
    if (!table_exists('area_success_geocodes')) return null;
    $st=db()->prepare('SELECT latitude,longitude,display_name,status FROM area_success_geocodes WHERE area_key=? LIMIT 1');
    $st->execute([strtolower(trim($kecamatan))]); $row=$st->fetch();
    if($row&&$row['status']==='ok'&&$row['latitude']!==null&&$row['longitude']!==null)
        return ['latitude'=>(float)$row['latitude'],'longitude'=>(float)$row['longitude'],'display_name'=>(string)($row['display_name']??$kecamatan)];
    return null;
}

function area_success_snapshot(): array {
    $rows=fetch_sheet(false); $kecs=[];
    foreach($rows as $row){
        $address=trim((string)($row['address']??'')); if($address==='')continue;
        $area=area_success_locality($address); $ctx=area_success_context($address,$area); $kec=$ctx['kecamatan'];
        if($kec==='')continue;
        if(!isset($kecs[$kec]))$kecs[$kec]=['name'=>$kec,'close'=>0,'open'=>0,'total'=>0,'areas'=>[]];
        $kecs[$kec]['total']++;
        if(sheet_bucket($row)==='close')$kecs[$kec]['close']++;
        $areaKey=$area==='LAINNYA'?'LAINNYA':$area;
        if(!isset($kecs[$kec]['areas'][$areaKey]))$kecs[$kec]['areas'][$areaKey]=['area'=>$areaKey,'close'=>0,'open'=>0,'total'=>0,'customers'=>[]];
        $kecs[$kec]['areas'][$areaKey]['total']++;
        if(sheet_bucket($row)==='close')$kecs[$kec]['areas'][$areaKey]['close']++;
        $kecs[$kec]['areas'][$areaKey]['customers'][]=[
            'service_number'=>(string)($row['service_number']??''),'customer_name'=>(string)($row['customer_name']??''),
            'address'=>$address,'status'=>(string)($row['status']??''),'ticket_id'=>(string)($row['ticket_id']??''),
            'customer_phone'=>(string)($row['customer_phone']??''),'assigned_technician'=>(string)($row['assigned_technician']??'')
        ];
    }
    foreach($kecs as &$k){
        $k['open']=max(0,$k['total']-$k['close']); $k['rate']=$k['total']?round($k['close']/$k['total']*100,1):0;
        $k['color']=area_success_color($k['rate']); $geo=area_success_geocode_cached($k['name']);
        $k['latitude']=$geo['latitude']??null; $k['longitude']=$geo['longitude']??null; $k['display_name']=$geo['display_name']??('Kecamatan '.$k['name']); $k['geocoded']=$geo!==null; $k['coordinate_count']=$geo?1:0; $k['radius_m']=1200;
        foreach($k['areas'] as &$a){$a['open']=max(0,$a['total']-$a['close']);$a['rate']=$a['total']?round($a['close']/$a['total']*100,1):0;}
        unset($a); $k['areas']=array_values($k['areas']);
    } unset($k);
    uasort($kecs,static fn($a,$b)=>($b['total']<=>$a['total'])?:strcmp($a['name'],$b['name']));
    return ['ok'=>true,'source'=>'GOOGLE SHEET CURRENT ORDERS','success_definition'=>'CLOSE / TOTAL ORDER PER KECAMATAN','level'=>'KECAMATAN','areas'=>array_values($kecs),'area_count'=>count($kecs),'geocoded_count'=>count(array_filter($kecs,static fn($x)=>(bool)$x['geocoded']))];
}

function area_success_detail(string $kecamatan): array {
    $snapshot=area_success_snapshot();
    foreach($snapshot['areas'] as $k) if(strcasecmp($k['name'],$kecamatan)===0) return ['ok'=>true,'level'=>'KECAMATAN','kecamatan'=>$k['name'],'close'=>$k['close'],'open'=>$k['open'],'total'=>$k['total'],'rate'=>$k['rate'],'areas'=>$k['areas']];
    return ['ok'=>false,'error'=>'kecamatan_not_found','message'=>'Kecamatan tidak ditemukan.'];
}
