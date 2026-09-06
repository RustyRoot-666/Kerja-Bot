<?php

declare(strict_types=1);

require_once __DIR__.'/php_backend.php';
require_once __DIR__.'/php_compat.php';

/**
 * Dashboard fallback for installations where the report tables are empty or
 * have not yet been rebuilt. Uses the canonical orders table instead.
 */
function dashboard_orders_fallback(string $area, string $period): array {
    $area = strtoupper(trim($area ?: 'ALL'));
    $period = strtolower(trim($period ?: 'daily'));
    if (!in_array($period, ['daily','weekly','all'], true)) $period = 'daily';

    $today = new DateTimeImmutable('today');
    [$weekStart,$weekEnd] = period_bounds($today);
    $where = ['1=1'];
    $params = [];

    if ($period === 'daily') {
        $where[] = "substr(updated_at,1,10)=?";
        $params[] = $today->format('Y-m-d');
        $label = date_label($today);
    } elseif ($period === 'weekly') {
        $where[] = "substr(updated_at,1,10)>=? AND substr(updated_at,1,10)<=?";
        $params[] = $weekStart->format('Y-m-d');
        $params[] = $weekEnd->format('Y-m-d');
        $label = date_label($weekStart).' - '.date_label($weekEnd);
    } else {
        $label = 'Keseluruhan';
    }

    if ($area === 'MYR') {
        $where[] = "UPPER(TRIM(sto))='MYR'";
    } elseif ($area === 'JGR') {
        $where[] = "UPPER(TRIM(sto))='JGR'";
    }

    $where[] = "UPPER(TRIM(result)) IN ('CLOSE','CLOSED','DONE','SELESAI','COMPLETED')";
    $st = db()->prepare('SELECT assigned_technician,service_number,sto,updated_at FROM orders WHERE '.implode(' AND ',$where));
    $st->execute($params);
    $rows = $st->fetchAll();

    $groups = [];
    foreach ($rows as $r) {
        $name = trim((string)($r['assigned_technician'] ?? ''));
        if ($name === '') $name = 'TANPA TEKNISI';
        $key = norm_name($name);
        if ($key === '') $key = 'TANPA TEKNISI';
        $service = norm_key($r['service_number'] ?? '');
        if ($service === '') continue;
        if (!isset($groups[$key])) {
            $groups[$key] = [
                'name'=>$name,
                'services'=>[],
                'latest'=>'',
                'sto'=>'',
                'area_label'=>'',
            ];
        }
        $groups[$key]['services'][$service] = true;
        $day = substr((string)($r['updated_at'] ?? ''),0,10);
        if ($day >= $groups[$key]['latest']) {
            $groups[$key]['latest'] = $day;
            $groups[$key]['sto'] = strtoupper(trim((string)($r['sto'] ?? '')));
            $groups[$key]['area_label'] = $groups[$key]['sto'] ?: '-';
        }
    }

    $registry = technician_registry();
    $leaderboard = [];
    foreach ($groups as $g) {
        $reg = $registry[norm_name($g['name'])] ?? [];
        $leaderboard[] = [
            'key'=>'NAME:'.norm_name($g['name']),
            'nik'=>(string)($reg['nik'] ?? ''),
            'name'=>(string)$g['name'],
            'total'=>count($g['services']),
            'area_label'=>$g['area_label'],
            'sto'=>$g['sto'],
        ];
    }
    usort($leaderboard, fn($a,$b) => $b['total'] <=> $a['total'] ?: strcmp(norm_name($a['name']),norm_name($b['name'])));

    $trend=[];
    for ($i=6;$i>=0;$i--) {
        $d=$today->modify("-$i days");
        $trendWhere=["substr(updated_at,1,10)=?","UPPER(TRIM(result)) IN ('CLOSE','CLOSED','DONE','SELESAI','COMPLETED')"];
        $trendParams=[$d->format('Y-m-d')];
        if ($area==='MYR') $trendWhere[]="UPPER(TRIM(sto))='MYR'";
        elseif ($area==='JGR') $trendWhere[]="UPPER(TRIM(sto))='JGR'";
        $ts=db()->prepare('SELECT service_number FROM orders WHERE '.implode(' AND ',$trendWhere));
        $ts->execute($trendParams);
        $services=[];
        foreach($ts->fetchAll() as $tr){$s=norm_key($tr['service_number']??'');if($s!=='')$services[$s]=1;}
        $trend[]=['date'=>$d->format('Y-m-d'),'label'=>DAYS_ID[((int)$d->format('N'))-1],'total'=>count($services)];
    }

    $total=array_sum(array_column($leaderboard,'total'));
    $active=count($leaderboard);
    return [
        'area'=>$area,
        'period'=>$period,
        'period_label'=>$label,
        'summary'=>[
            'total_close'=>$total,
            'active_technicians'=>$active,
            'average_close'=>$active?round($total/$active,1):0,
        ],
        'trend'=>$trend,
        'leaderboard'=>$leaderboard,
        'rca_summary'=>load_rca_summary_php($area),
        'backend'=>'php-orders-fallback',
    ];
}
