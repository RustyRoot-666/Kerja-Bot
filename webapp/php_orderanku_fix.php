<?php

declare(strict_types=1);

function orderanku_sheet_bucket(array $row): string {
    $status = norm($row['status'] ?? '');

    if (
        in_array($status, CLOSED_STATUSES, true)
        || str_contains($status, 'CLOSE')
        || str_contains($status, 'CLOSED')
        || str_contains($status, 'DONE')
        || str_contains($status, 'SELESAI')
        || str_contains($status, 'COMPLET')
    ) {
        return 'close';
    }

    if (
        in_array($status, UPDATE_STATUSES, true)
        || str_contains($status, 'UPDATE')
        || str_contains($status, 'PROGRESS')
        || str_contains($status, 'PENDING')
    ) {
        return 'update';
    }

    return 'open';
}

function load_my_open_orders_fixed(int $telegramId, bool $force=false): array {
    $tech = technician_by_telegram($telegramId);
    if (!$tech) {
        return [
            'ok' => false,
            'error' => 'technician_not_registered',
            'message' => 'Akun Telegram belum terdaftar sebagai teknisi.',
        ];
    }

    $refs = fetch_sheet($force);
    $wanted = norm_name($tech['name'] ?? '');
    $summary = [];
    $groups = [];

    foreach ($refs as $row) {
        if (norm_name($row['assigned_technician'] ?? '') !== $wanted) continue;

        $area = classify_area((string)($row['address'] ?? ''));
        $bucket = orderanku_sheet_bucket($row);
        $summary[$area] ??= ['open' => 0, 'close' => 0, 'update' => 0];
        $summary[$area][$bucket]++;

        if ($bucket === 'open') {
            $groups[$area][] = order_payload($row);
        }
    }

    $areas = [];
    foreach ($groups as $area => $orders) {
        usort($orders, fn($a, $b) => strnatcasecmp($a['address'], $b['address']));
        $counts = $summary[$area] ?? ['open' => 0, 'close' => 0, 'update' => 0];
        $areas[] = [
            'area' => $area,
            'open' => count($orders),
            'close' => (int)$counts['close'],
            'update' => (int)$counts['update'],
            'orders' => $orders,
        ];
    }

    $jagir = my_jagir_orders($telegramId, $tech);
    if ($jagir) {
        $areas[] = [
            'area' => 'JAGIR',
            'open' => count($jagir),
            'close' => 0,
            'update' => 0,
            'orders' => $jagir,
        ];
    }

    usort(
        $areas,
        fn($a, $b) => ($a['area'] === 'JAGIR' ? 1 : 0) <=> ($b['area'] === 'JAGIR' ? 1 : 0)
            ?: strcmp($a['area'], $b['area'])
    );

    return [
        'ok' => true,
        'technician' => [
            'telegram_id' => $telegramId,
            'nik' => $tech['nik'],
            'name' => $tech['name'],
            'sto' => $tech['sto'],
        ],
        'source' => 'ORDER SHEET (MYR) + WORK ORDER JAGIR (JGR)',
        'total_open' => array_sum(array_column($areas, 'open')),
        'active_areas' => count($areas),
        'areas' => $areas,
    ];
}
