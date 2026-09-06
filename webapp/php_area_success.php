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

    // Customer-area key: keep the street/building name and stop at the
    // house/section number. This preserves names such as
    // "KEDUNG TARUKAN BARU" instead of incorrectly using the final
    // administrative token (for example MOJO).
    $s = preg_replace('/\bNO\.?\s*\d+[A-Z]?\b.*$/i', '', $s) ?: $s;
    $s = preg_replace('/\bNOMER\s*\d+[A-Z]?\b.*$/i', '', $s) ?: $s;
    $tokens = preg_split('/\s+/', trim($s)) ?: [];
    $roman = '/^(?:I|II|III|IV|V|VI|VII|VIII|IX|X|XI|XII|XIII|XIV|XV|XVI|XVII|XVIII|XIX|XX)$/';

    $kept = [];
    foreach ($tokens as $token) {
        $token = trim($token);
        if ($token === '') continue;
        if (preg_match('/^\d+[A-Z]?$/', $token) || preg_match($roman, strtoupper($token))) break;
        $kept[] = $token;
    }

    $candidate = trim(implode(' ', $kept));
    if ($candidate === '') $candidate = $s;

    // Remove common street prefixes; the map should show the customer area,
    // not the transport/address prefix.
    $candidate = preg_replace('/^(?:JL\.?|JALAN|GG\.?|GANG)\s+/i', '', $candidate) ?: $candidate;
    $candidate = trim(preg_replace('/\s+/', ' ', $candidate) ?: '');
    if ($candidate === '') return 'LAINNYA';

    // Apartment addresses are represented by the building name only.
    if (preg_match('/^(?:APARTEMEN|APARTEMENT)\s+(.+?)(?:\s+[A-Z]?\d+[A-Z]?)?$/i', $candidate, $m)) {
        $candidate = 'APARTEMEN ' . trim($m[1]);
    }

    return strtoupper($candidate);
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
