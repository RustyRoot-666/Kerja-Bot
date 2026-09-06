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

    // Remove explicit house-number suffix first. The remaining text is the
    // customer locality/building portion used by Area Success.
    $s = preg_replace('/\b(?:NO|NOMER)\.?\s*[A-Z]?\d+[A-Z]?\b.*$/i', '', $s) ?: $s;
    $s = preg_replace('/\s+/', ' ', trim($s)) ?: $s;

    // Strip address prefixes that are not part of the locality label.
    $s = preg_replace('/^(?:JL\.?|JALAN|GG\.?|GANG)\s+/i', '', $s) ?: $s;
    $tokens = preg_split('/\s+/', trim($s)) ?: [];
    if (!$tokens) return 'LAINNYA';

    // Apartment/building names need special treatment because tower, unit,
    // floor, and section labels belong to the same physical complex.
    if (preg_match('/^(?:APARTEMEN|APARTEMENT|APARTMENT)\s+(.+)$/i', $s, $m)) {
        $building = trim($m[1]);
        $building = preg_replace('/\s+TOWER(?:\s+[A-Z0-9]+)?(?:\s+.*)?$/i', '', $building) ?: $building;
        $building = preg_replace('/\s+UNIT(?:\s+[A-Z0-9]+)?(?:\s+.*)?$/i', '', $building) ?: $building;
        $building = preg_replace('/\s+(?:LT|LANTAI)\s*\d+.*$/i', '', $building) ?: $building;
        $building = preg_replace('/\s+[A-Z]\s+(?:UTARA|SELATAN|TIMUR|BARAT)(?:\s+.*)?$/i', '', $building) ?: $building;
        // Known Education City tower names are tower labels under one complex.
        $building = preg_replace('/\s+(?:HARVARD|YALE|PRINCETON|STAMFORD)\s*$/i', '', $building) ?: $building;
        $building = preg_replace('/\s+[A-Z]$/i', '', $building) ?: $building;
        $building = trim($building);
        if ($building === '') $building = trim($m[1]);
        return strtoupper('APARTEMEN ' . $building);
    }

    // Street/area grouping: stop at the first numeric/mixed block/house token,
    // Roman section token, or common unit/floor marker. This keeps e.g.
    // KEDUNG TARUKAN BARU 4 55 as KEDUNG TARUKAN BARU.
    $roman = '/^(?:I|II|III|IV|V|VI|VII|VIII|IX|X|XI|XII|XIII|XIV|XV|XVI|XVII|XVIII|XIX|XX)$/i';
    $kept = [];
    foreach ($tokens as $token) {
        $token = trim($token);
        if ($token === '') continue;
        if (preg_match('/^(?:LT|LANTAI)\d+[A-Z]?$/i', $token)
            || preg_match('/^[A-Z]+\d+[A-Z]?$/i', $token)
            || preg_match('/^\d+[A-Z]?$/i', $token)
            || preg_match($roman, $token)) {
            break;
        }
        $kept[] = $token;
    }

    $candidate = trim(implode(' ', $kept));
    if ($candidate === '') $candidate = trim($s);

    // A final single-letter block is generally a house/section detail.
    $candidate = preg_replace('/\s+[A-Z]$/i', '', $candidate) ?: $candidate;
    $candidate = trim(preg_replace('/\s+/', ' ', $candidate) ?: '');
    return $candidate !== '' ? strtoupper($candidate) : 'LAINNYA';
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
