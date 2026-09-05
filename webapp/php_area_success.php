<?php

declare(strict_types=1);

/**
 * Area success map for the main supervisor dashboard.
 *
 * A range is derived from the street/range prefix before the first standalone
 * house-block Roman numeral or numeric house number. This makes addresses such
 * as "SEMOLOWARU UTARA I 30" and "SEMOLOWARU UTARA V 15" belong to the same
 * operational range: "SEMOLOWARU UTARA".
 */
function area_success_normalize(string $address): string {
    $s = normalize_address($address);
    $s = preg_replace('/\b(?:SBY|SURABAYA|JAWA TIMUR|INDONESIA)\b.*$/', '', $s) ?: $s;
    return trim(preg_replace('/\s+/', ' ', $s) ?: '');
}

function area_success_range_key(string $address): string {
    $s = area_success_normalize($address);
    if ($s === '') return 'LAINNYA';
    $tokens = preg_split('/\s+/', $s) ?: [];
    $roman = '/^(?:I|II|III|IV|V|VI|VII|VIII|IX|X|XI|XII|XIII|XIV|XV|XVI|XVII|XVIII|XIX|XX)$/';
    $cut = count($tokens);
    foreach ($tokens as $i => $token) {
        if ($i >= 2 && (preg_match($roman, $token) || preg_match('/^\d+[A-Z]?$/', $token))) {
            $cut = $i;
            break;
        }
    }
    $prefix = trim(implode(' ', array_slice($tokens, 0, $cut)));
    if ($prefix === '') return classify_area($address);
    return $prefix;
}

function area_success_color(float $rate): string {
    if ($rate < 0.25) return '#ef4444';
    if ($rate < 0.50) return '#f97316';
    if ($rate < 0.75) return '#eab308';
    return '#22c55e';
}

function area_success_distance_m(float $lat1, float $lng1, float $lat2, float $lng2): float {
    $r = 6371000.0;
    $p1 = deg2rad($lat1); $p2 = deg2rad($lat2);
    $dp = deg2rad($lat2 - $lat1); $dl = deg2rad($lng2 - $lng1);
    $a = sin($dp / 2) ** 2 + cos($p1) * cos($p2) * sin($dl / 2) ** 2;
    return 2 * $r * asin(min(1.0, sqrt($a)));
}

function area_success_geocode_cached(string $address): ?array {
    customer_zone_ensure_schema();
    $key = customer_zone_key($address);
    $st = db()->prepare('SELECT latitude,longitude,display_name,status FROM customer_geocodes WHERE address_key=? LIMIT 1');
    $st->execute([$key]);
    $row = $st->fetch();
    if ($row && $row['status'] === 'ok' && $row['latitude'] !== null && $row['longitude'] !== null) {
        return ['latitude'=>(float)$row['latitude'], 'longitude'=>(float)$row['longitude'], 'display_name'=>(string)($row['display_name'] ?? '')];
    }
    return null;
}

function area_success_snapshot(): array {
    require_once __DIR__.'/php_customer_zones.php';
    $rows = fetch_sheet(false);
    $areas = [];
    foreach ($rows as $row) {
        $address = trim((string)($row['address'] ?? ''));
        if ($address === '') continue;
        $key = area_success_range_key($address);
        $areas[$key] ??= [
            'range'=>$key, 'open'=>0, 'close'=>0, 'total'=>0,
            'rate'=>0, 'color'=>'#ef4444', 'addresses'=>[], 'points'=>[]
        ];
        $bucket = sheet_bucket($row);
        if ($bucket === 'close') $areas[$key]['close']++;
        elseif ($bucket === 'open') $areas[$key]['open']++;
        $areas[$key]['total']++;
        $areas[$key]['addresses'][$address] = true;
    }

    $missing = [];
    foreach ($areas as $key => &$area) {
        $area['addresses'] = array_keys($area['addresses']);
        foreach ($area['addresses'] as $address) {
            $geo = area_success_geocode_cached($address);
            if ($geo) $area['points'][] = [$geo['latitude'], $geo['longitude']];
        }
        if (!$area['points'] && $area['addresses']) $missing[] = [$key, $area['addresses'][0]];
    }
    unset($area);

    // At most a few new Nominatim requests per dashboard refresh. Existing
    // customer_geocodes are reused, so normal refreshes do not hammer geocoding.
    $geoBudget = 8;
    foreach ($missing as [$key, $address]) {
        if ($geoBudget <= 0) break;
        $geo = customer_zone_geocode($address);
        $now = date('Y-m-d H:i:s');
        $ckey = customer_zone_key($address);
        if ($geo) {
            db()->prepare("INSERT INTO customer_geocodes(address_key,address,latitude,longitude,display_name,status,attempts,updated_at) VALUES(?,?,?,?,?,'ok',1,?) ON CONFLICT(address_key) DO UPDATE SET latitude=excluded.latitude,longitude=excluded.longitude,display_name=excluded.display_name,status='ok',attempts=customer_geocodes.attempts+1,updated_at=excluded.updated_at")
                ->execute([$ckey,$address,$geo['latitude'],$geo['longitude'],$geo['display_name'],$now]);
            $areas[$key]['points'][] = [$geo['latitude'], $geo['longitude']];
        }
        $geoBudget--;
        usleep(1100000);
    }

    foreach ($areas as &$area) {
        $area['rate'] = $area['total'] > 0 ? round(($area['close'] / $area['total']) * 100, 1) : 0;
        $area['color'] = area_success_color($area['rate'] / 100);
        $points = $area['points'];
        if ($points) {
            $lat = array_sum(array_column($points, 0)) / count($points);
            $lng = array_sum(array_column($points, 1)) / count($points);
            $radius = 180.0;
            foreach ($points as $p) $radius = max($radius, area_success_distance_m($lat, $lng, $p[0], $p[1]) + 80.0);
            $area['latitude'] = $lat;
            $area['longitude'] = $lng;
            $area['radius_m'] = min(900.0, $radius);
            $area['geocoded'] = true;
        } else {
            $area['latitude'] = null;
            $area['longitude'] = null;
            $area['radius_m'] = null;
            $area['geocoded'] = false;
        }
        unset($area['addresses'], $area['points']);
    }
    unset($area);

    uasort($areas, static fn($a, $b) => ($b['rate'] <=> $a['rate']) ?: strcmp($a['range'], $b['range']));
    return [
        'ok'=>true,
        'source'=>'GOOGLE SHEET CURRENT ORDERS',
        'success_definition'=>'CLOSE / TOTAL ORDER',
        'areas'=>array_values($areas),
        'area_count'=>count($areas),
        'geocoded_count'=>count(array_filter($areas, static fn($a)=>(bool)$a['geocoded'])),
    ];
}
