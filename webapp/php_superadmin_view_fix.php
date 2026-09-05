<?php

declare(strict_types=1);

// This helper is also used directly by diagnostic/CLI scripts. Keep its
dependencies explicit so it can never rely on router include order.
require_once __DIR__.'/php_backend.php';
require_once __DIR__.'/php_compat.php';

/**
 * Supervisor/Superadmin view fixes.
 * Keeps normal technicians scoped to their own orders while making
 * admin/superadmin views read the complete operational dataset.
 */

function superadmin_open_orders_php(bool $force=false): array {
    $byKey = [];

    // Primary source: current Google Order Sheet (MYR).
    try {
        foreach (fetch_sheet($force) as $row) {
            if (sheet_bucket($row) !== 'open') continue;
            $service = norm_key($row['service_number'] ?? '');
            $ticket = norm_key($row['ticket_id'] ?? '');
            $key = $service !== '' ? 'INET:' . $service : 'TICKET:' . $ticket;
            if ($key === 'INET:' || $key === 'TICKET:') continue;
            $order = order_payload($row, 'ORDER SHEET');
            $order['technician_name'] = clean($row['assigned_technician'] ?? '') ?: '-';
            $order['technician_nik'] = '';
            $byKey[$key] = $order;
        }
    } catch (Throwable $e) {
        error_log('[miniapp-php] superadmin sheet orders unavailable: ' . $e->getMessage());
    }

    // Secondary source: open JAGIR work orders.
    if (table_exists('jagir_work_orders')) {
        try {
            $rows = db()->query("SELECT * FROM jagir_work_orders WHERE UPPER(TRIM(status))='OPEN' ORDER BY address,service_number")->fetchAll();
            foreach ($rows as $row) {
                $order = wo_payload($row);
                $service = norm_key($order['service_number'] ?? '');
                $ticket = norm_key($order['ticket_id'] ?? '');
                $key = $service !== '' ? 'INET:' . $service : 'TICKET:' . $ticket;
                if ($key === 'INET:' || $key === 'TICKET:') continue;
                $order['technician_name'] = clean($row['assigned_name'] ?? '') ?: (($row['assigned_username'] ?? '') ? '@' . trim((string)$row['assigned_username']) : '-');
                $order['technician_nik'] = clean($row['assigned_nik'] ?? '');
                $byKey[$key] = $order;
            }
        } catch (Throwable $e) {
            error_log('[miniapp-php] superadmin JAGIR orders unavailable: ' . $e->getMessage());
        }
    }

    $areas = [];
    foreach ($byKey as $order) {
        $area = strtoupper(trim((string)($order['area'] ?? '')));
        if ($area === '') $area = classify_area((string)($order['address'] ?? ''));
        $areas[$area] ??= ['area'=>$area,'open'=>0,'close'=>0,'update'=>0,'orders'=>[]];
        $areas[$area]['open']++;
        $areas[$area]['orders'][] = $order;
    }

    foreach ($areas as &$area) {
        usort($area['orders'], static fn($a,$b) =>
            strcmp((string)($a['technician_name'] ?? ''),(string)($b['technician_name'] ?? ''))
            ?: strnatcasecmp((string)($a['address'] ?? ''),(string)($b['address'] ?? ''))
        );
    }
    unset($area);

    uksort($areas, static fn($a,$b) =>
        ($a === 'JAGIR' ? 1 : 0) <=> ($b === 'JAGIR' ? 1 : 0) ?: strcmp($a,$b)
    );
    $areas = array_values($areas);

    return [
        'ok'=>true,
        'technician'=>['telegram_id'=>0,'nik'=>'ALL','name'=>'SEMUA TEKNISI','sto'=>'ALL'],
        'source'=>'ORDER SHEET (MYR) + WORK ORDER JAGIR (JGR)',
        'total_open'=>array_sum(array_column($areas,'open')),
        'active_areas'=>count($areas),
        'areas'=>$areas,
        'supervisor'=>true,
        'read_only'=>true,
        'can_filter_nik'=>true,
        'selected_nik'=>'ALL',
    ];
}

function superadmin_history_rows_php(string $area, string $period): array {
    if (!table_exists('histories')) return [];

    $area = strtoupper(trim($area));
    $today = new DateTimeImmutable('today');
    [$weekStart,$weekEnd] = period_bounds($today);
    $where = "UPPER(TRIM(kind))='REPORT'";
    $params = [];

    if ($period === 'daily') {
        $where .= ' AND substr(created_at,1,10)=?';
        $params[] = $today->format('Y-m-d');
    } elseif ($period === 'weekly') {
        $where .= ' AND substr(created_at,1,10)>=? AND substr(created_at,1,10)<=?';
        $params[] = $weekStart->format('Y-m-d');
        $params[] = $weekEnd->format('Y-m-d');
    }

    if (in_array($area,['MYR','JGR'],true)) {
        $where .= " AND UPPER(TRIM(COALESCE(sto,'')))=?";
        $params[] = $area;
    }

    $sql = "SELECT telegram_id, technician_id, ticket_id, service_number, sto, created_at
            FROM histories WHERE $where ORDER BY created_at ASC, id ASC";
    $st = db()->prepare($sql);
    $st->execute($params);
    return $st->fetchAll();
}

function superadmin_dashboard_from_history_php(string $area, string $period): array {
    $area = strtoupper(trim($area ?: 'ALL'));
    $period = strtolower(trim($period ?: 'daily'));
    if (!in_array($period,['daily','weekly','all'],true)) $period='daily';

    $today = new DateTimeImmutable('today');
    [$weekStart,$weekEnd] = period_bounds($today);
    $label = 'Keseluruhan';
    if ($period === 'daily') $label = date_label($today);
    elseif ($period === 'weekly') $label = date_label($weekStart) . ' - ' . date_label($weekEnd);

    $rows = superadmin_history_rows_php($area,$period);
    $techRegistry = [];
    if (table_exists('technicians')) {
        foreach (db()->query('SELECT telegram_id,nik,name,sto FROM technicians WHERE is_active=1')->fetchAll() as $t) {
            $techRegistry[(string)$t['telegram_id']] = $t;
        }
    }

    $groups=[];
    foreach ($rows as $r) {
        $tid=(string)($r['telegram_id']??'');
        $reg=$techRegistry[$tid]??[];
        $name=trim((string)($reg['name']??''));
        if ($name==='') $name='TEKNISI ' . $tid;
        $nik=trim((string)($reg['nik']??$r['nik']??''));
        $key=$tid!==''?'TG:'.$tid:'NAME:'.norm_name($name);
        $groups[$key]??=[
            'key'=>$key,'nik'=>$nik,'name'=>$name,
            'sto'=>strtoupper(trim((string)($reg['sto']??$r['sto']??''))),
            'services'=>[],'latest'=>'','area_label'=>''
        ];
        $service=norm_key($r['service_number']??'');
        if ($service!=='') $groups[$key]['services'][$service]=1;
        $created=(string)($r['created_at']??'');
        if ($created >= $groups[$key]['latest']) $groups[$key]['latest']=$created;
    }

    $leader=[];
    foreach ($groups as $g) {
        $leader[]=[
            'key'=>$g['key'],'nik'=>$g['nik'],'name'=>$g['name'],
            'total'=>count($g['services']),'area_label'=>$g['sto'] ?: ($area==='ALL'?'SEMUA':$area),
            'sto'=>$g['sto'] ?: ($area==='ALL'?'ALL':$area)
        ];
    }
    usort($leader,static fn($a,$b)=>(int)$b['total']<=>(int)$a['total'] ?: strcmp(norm_name($a['name']),norm_name($b['name'])));

    $trend=[];
    for ($i=6;$i>=0;$i--) {
        $d=$today->modify("-$i days");
        $day=$d->format('Y-m-d');
        $seen=[];
        foreach (superadmin_history_rows_php($area,'all') as $r) {
            if (substr((string)($r['created_at']??''),0,10)!==$day) continue;
            $s=norm_key($r['service_number']??'');
            if ($s!=='') $seen[$s]=1;
        }
        $trend[]=['date'=>$day,'label'=>DAYS_ID[((int)$d->format('N'))-1],'total'=>count($seen)];
    }

    $total=array_sum(array_column($leader,'total'));
    $active=count($leader);
    return [
        'ok'=>true,
        'area'=>$area,'period'=>$period,'period_label'=>$label,
        'summary'=>['total_close'=>$total,'active_technicians'=>$active,'average_close'=>$active?round($total/$active,1):0],
        'trend'=>$trend,'leaderboard'=>$leader,
        'rca_summary'=>load_rca_summary_php($area),
        'backend'=>'php','data_source'=>'histories REPORT + Google Sheet RCA'
    ];
}

function load_superadmin_dashboard_php(string $area,string $period): array {
    $payload = superadmin_dashboard_from_history_php($area,$period);

    // Prefer the established report tables when they actually contain data.
    // The history fallback is required after database recovery and when report
    // aggregation tables have not yet been rebuilt.
    if ((int)($payload['summary']['total_close']??0) === 0 && table_exists('report_group_orders')) {
        try {
            $legacy = load_dashboard_php($area,$period);
            if ((int)($legacy['summary']['total_close']??0) > 0) return $legacy;
        } catch (Throwable $e) {
            error_log('[miniapp-php] legacy dashboard fallback failed: '.$e->getMessage());
        }
    }
    return $payload;
}
