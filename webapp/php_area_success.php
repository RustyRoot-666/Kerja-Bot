<?php

declare(strict_types=1);

function area_success_normalize(string $address): string {
    $s = normalize_address($address);
    $s = preg_replace('/\b(?:SBY|SURABAYA|JAWA TIMUR|INDONESIA)\b.*$/', '', $s) ?: $s;
    return trim(preg_replace('/\s+/', ' ', $s) ?: '');
}

function area_success_color(float $rate): string {
    if ($rate < 0.25) return '#ef4444';
    if ($rate < 0.50) return '#f97316';
    if ($rate < 0.75) return '#eab308';
    return '#22c55e';
}

function area_success_locality(string $address): string {
    $s = area_success_normalize($address);
    if ($s === '') return 'LAINNYA';
    $tokens = preg_split('/\s+/', $s) ?: [];
    $roman = '/^(?:I|II|III|IV|V|VI|VII|VIII|IX|X|XI|XII|XIII|XIV|XV|XVI|XVII|XVIII|XIX|XX)$/';
    while ($tokens && (preg_match('/^\d+[A-Z]?$/', end($tokens)) || preg_match($roman, end($tokens)))) array_pop($tokens);
    if (!$tokens) return 'LAINNYA';

    $aliases = [
        'TENGGILIS MEJOYO','TENGGILIS','GUNUNG ANYAR','WIYUNG','LAKARSANTRI',
        'SUKOLILO','MULYOREJO','RUNGKUT','GUBENG','KARANG PILANG','KARANGPILANG',
        'DUKUH PAKIS','SAWAHAN','WONOKROMO','WONOCOLO','JAMBANGAN','GAYUNGAN',
        'SIMOKERTO','BENOWO','PAKAL','ASEMROWO','TAMBAKSARI','SEMAMPIR','KENJERAN',
        'BULAK','KREMBANGAN','PABEAN CANTIAN','TEGALSARI','GENTENG','BUBUTAN',
        'SUKOMANUNGGAL','TANDES','MOJO','KERTAJAYA','AIRLANGGA','KEPUTIH','NGINDEN',
        'PUMPUNGAN','MENUR','SEMOLOWARU','MANYAR'
    ];
    $upper = strtoupper(implode(' ', $tokens));
    foreach ($aliases as $alias) {
        $alias = strtoupper($alias);
        if (preg_match('/(?:^| )'.preg_quote($alias,'/').'$/', $upper)) return $alias;
    }
    return strtoupper((string)end($tokens));
}

function area_success_geocode_cached(string $area): ?array {
    if (!table_exists('area_success_geocodes')) return null;
    $st = db()->prepare('SELECT latitude,longitude,display_name,status FROM area_success_geocodes WHERE area_key=? LIMIT 1');
    $st->execute([strtolower(trim($area))]);
    $row = $st->fetch();
    if ($row && $row['status'] === 'ok' && $row['latitude'] !== null && $row['longitude'] !== null) {
        return ['latitude'=>(float)$row['latitude'],'longitude'=>(float)$row['longitude'],'display_name'=>(string)($row['display_name'] ?? $area)];
    }
    return null;
}

function area_success_snapshot(): array {
    $rows = fetch_sheet(false);
    $areas = [];
    foreach ($rows as $row) {
        $address = trim((string)($row['address'] ?? ''));
        if ($address === '') continue;
        $area = area_success_locality($address);
        $areas[$area] ??= ['range'=>$area,'area'=>$area,'open'=>0,'close'=>0,'total'=>0,'rate'=>0,'color'=>'#ef4444'];
        $areas[$area]['total']++;
        if (sheet_bucket($row) === 'close') $areas[$area]['close']++;
    }

    foreach ($areas as &$item) {
        $item['open'] = max(0, $item['total'] - $item['close']);
        $item['rate'] = $item['total'] > 0 ? round(($item['close'] / $item['total']) * 100, 1) : 0;
        $item['color'] = area_success_color($item['rate'] / 100);
        $geo = area_success_geocode_cached($item['area']);
        $item['latitude'] = $geo['latitude'] ?? null;
        $item['longitude'] = $geo['longitude'] ?? null;
        $item['display_name'] = $geo['display_name'] ?? $item['area'];
        $item['geocoded'] = $geo !== null;
        $item['coordinate_count'] = $geo !== null ? 1 : 0;
        $item['radius_m'] = 500;
    }
    unset($item);

    uasort($areas, static fn($a,$b) => ($b['rate'] <=> $a['rate']) ?: strcmp($a['area'],$b['area']));
    return [
        'ok'=>true,
        'source'=>'GOOGLE SHEET CURRENT ORDERS',
        'success_definition'=>'CLOSE / TOTAL ORDER PER CUSTOMER AREA',
        'areas'=>array_values($areas),
        'area_count'=>count($areas),
        'geocoded_count'=>count(array_filter($areas, static fn($a)=>(bool)$a['geocoded']))
    ];
}
