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

    // Prefer known multi-word customer localities before the final locality token.
    $aliases = [
        'TENGGILIS MEJOYO','TENGGILIS','GUNUNG ANYAR','WIYUNG','LAKARSANTRI',
        'SUKOLILO','MULYOREJO','RUNGKUT','GUBENG','KARANG PILANG','KARANGPILANG',
        'DUKUH PAKIS','SAWAHAN','WONOKROMO','WONOCOLO','JAMBANGAN','GAYUNGAN',
        'SAMBikEREP','BENOWO','PAKAL','ASEMROWO','TAMBAKSARI','SIMOKERTO',
        'SEMAMPIR','KENJERAN','BULAK','KREMBANGAN','PABEAN CANTIAN','KREMBANGAN',
        'TEGALSARI','GENTENG','BUBUTAN','SUKOMANUNGGAL','TANDES','KARANGPILANG'
    ];
    $upper = strtoupper(implode(' ', $tokens));
    foreach ($aliases as $alias) {
        $alias = strtoupper($alias);
        if (preg_match('/(?:^| )'.preg_quote($alias,'/').'$/', $upper)) return $alias;
    }
    return strtoupper((string)end($tokens));
}

function area_success_geocode_area(string $area): ?array {
    static $cache = [];
    $area = strtoupper(trim($area));
    if ($area === '' || $area === 'LAINNYA') return null;
    if (array_key_exists($area, $cache)) return $cache[$area];
    $query = $area . ', Surabaya, Jawa Timur, Indonesia';
    $url = 'https://nominatim.openstreetmap.org/search?' . http_build_query([
        'q'=>$query,'format'=>'jsonv2','limit'=>1,'countrycodes'=>'id'
    ]);
    $ctx = stream_context_create(['http'=>[
        'timeout'=>10,
        'header'=>"User-Agent: Kerja-Bot/1.0 (area-success-map)\r\nAccept: application/json\r\n"
    ]]);
    $raw = @file_get_contents($url, false, $ctx);
    if ($raw !== false) {
        $items = json_decode($raw, true);
        if (is_array($items) && !empty($items[0]['lat']) && !empty($items[0]['lon'])) {
            return $cache[$area] = [
                'latitude'=>(float)$items[0]['lat'],
                'longitude'=>(float)$items[0]['lon'],
                'display_name'=>(string)($items[0]['display_name'] ?? $area)
            ];
        }
    }
    return $cache[$area] = null;
}

function area_success_snapshot(): array {
    $rows = fetch_sheet(false);
    $areas = [];
    foreach ($rows as $row) {
        $address = trim((string)($row['address'] ?? ''));
        if ($address === '') continue;
        $area = area_success_locality($address);
        $areas[$area] ??= [
            'range'=>$area,'area'=>$area,'open'=>0,'close'=>0,'total'=>0,
            'rate'=>0,'color'=>'#ef4444'
        ];
        $areas[$area]['total']++;
        if (sheet_bucket($row) === 'close') $areas[$area]['close']++;
    }

    foreach ($areas as &$item) {
        $item['open'] = max(0, $item['total'] - $item['close']);
        $item['rate'] = $item['total'] > 0 ? round(($item['close'] / $item['total']) * 100, 1) : 0;
        $item['color'] = area_success_color($item['rate'] / 100);
        $geo = area_success_geocode_area($item['area']);
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
