<?php

declare(strict_types=1);

require_once __DIR__.'/php_backend.php';
require_once __DIR__.'/php_compat.php';

/**
 * Dashboard compatibility implementation.
 *
 * Historical dashboard data belongs to report_group_orders.message_date /
 * period_start. orders.updated_at is only the synchronization timestamp and
 * must never be used as the close date.
 */
function dashboard_orders_fallback(string $area, string $period): array {
    $area = strtoupper(trim($area ?: 'ALL'));
    $period = strtolower(trim($period ?: 'daily'));
    if (!in_array($period, ['daily','weekly','all'], true)) $period = 'daily';

    $today = new DateTimeImmutable('today');
    [$weekStart,$weekEnd] = period_bounds($today);
    $label = $period === 'daily'
        ? date_label($today)
        : ($period === 'weekly' ? date_label($weekStart).' - '.date_label($weekEnd) : 'Keseluruhan');

    $rows = [];
    $hasReport = table_exists('report_group_orders');
    if ($hasReport) {
        try {
            $count = (int)db()->query('SELECT COUNT(*) FROM report_group_orders')->fetchColumn();
            $hasReport = $count > 0;
        } catch (Throwable) {
            $hasReport = false;
        }
    }

    if ($hasReport) {
        // STO for historical reports is taken from the proven /STO recovery
        // table. Do not infer JGR/MYR from technician name or address.
        $areaSql = '1=1';
        $areaParams = [];
        if ($area === 'JGR' || $area === 'MYR') {
            $areaSql = "EXISTS (SELECT 1 FROM report_area_orders ra0 WHERE ra0.service_number=r.service_number AND ra0.period_start=r.period_start AND UPPER(TRIM(ra0.sto_code))=?)";
            $areaParams = [$area];
        }

        $timeSql = '1=1';
        $timeParams = [];
        if ($period === 'daily') {
            $timeSql = 'substr(r.message_date,1,10)=?';
            $timeParams = [$today->format('Y-m-d')];
        } elseif ($period === 'weekly') {
            // Dashboard week is Friday through Thursday.
            $timeSql = 'r.period_start=?';
            $timeParams = [$weekStart->format('Y-m-d')];
        }

        $sql = "SELECT r.technician_nik AS nik,
                       r.technician_name AS name,
                       r.service_number,
                       r.message_date,
                       UPPER(TRIM(COALESCE(NULLIF(ra.area_label,''), ra.sto_code, o.sto, ''))) AS area_label,
                       UPPER(TRIM(COALESCE(ra.sto_code, o.sto, ''))) AS sto
                FROM report_group_orders r
                LEFT JOIN report_area_orders ra ON ra.service_number=r.service_number AND ra.period_start=r.period_start
                LEFT JOIN orders o ON o.id=(SELECT o2.id FROM orders o2 WHERE o2.service_number=r.service_number ORDER BY o2.id DESC LIMIT 1)
                WHERE {$timeSql} AND {$areaSql}";
        $st = db()->prepare($sql);
        $st->execute(array_merge($timeParams,$areaParams));
        $rows = $st->fetchAll();
    } else {
        // Safe compatibility path for installations whose historical report
        // table has not been restored yet.
        $where = ["substr(updated_at,1,10)=?", "UPPER(TRIM(result)) IN ('CLOSE','CLOSED','DONE','SELESAI','COMPLETED')"];
        $params = [$today->format('Y-m-d')];
        if ($area === 'MYR') { $where[] = "UPPER(TRIM(sto))='MYR'"; }
        elseif ($area === 'JGR') { $where[] = "UPPER(TRIM(sto))='JGR'"; }
        $st = db()->prepare('SELECT assigned_technician AS name, service_number, updated_at AS message_date, sto FROM orders WHERE '.implode(' AND ',$where));
        $st->execute($params);
        $rows = $st->fetchAll();
    }

    $registry = technician_registry();
    $groups = [];
    $serviceDates = [];
    foreach ($rows as $r) {
        $service = norm_key($r['service_number'] ?? '');
        if ($service === '') continue;
        $name = trim((string)($r['name'] ?? $r['assigned_technician'] ?? ''));
        if ($name === '') continue;
        $key = norm_name($name);
        if ($key === '') continue;
        if (!isset($groups[$key])) $groups[$key] = [
            'name'=>$name,
            'nik'=>trim((string)($r['nik'] ?? '')),
            'services'=>[],
            'latest'=>'',
            'sto'=>'',
            'area_label'=>''
        ];
        $groups[$key]['services'][$service] = true;
        if ($groups[$key]['nik'] === '' && trim((string)($r['nik'] ?? '')) !== '') {
            $groups[$key]['nik'] = trim((string)$r['nik']);
        }
        $day = substr((string)($r['message_date'] ?? ''),0,10);
        if ($day >= $groups[$key]['latest']) {
            $groups[$key]['latest']=$day;
            $groups[$key]['sto']=strtoupper(trim((string)($r['sto'] ?? '')));
            $groups[$key]['area_label']=strtoupper(trim((string)($r['area_label'] ?? $r['sto'] ?? '')));
        }
        $serviceDates[$service][$day] = true;
    }

    $leaderboard=[];
    foreach ($groups as $g) {
        $reg=[];
        $nikKey=norm_key($g['nik'] ?? '');
        if ($nikKey !== '') $reg=$registry['NIK:'.$nikKey] ?? [];
        if (!$reg) $reg=$registry[norm_name($g['name'])] ?? [];
        $leaderboard[]=[
            'key'=>'NAME:'.norm_name($g['name']),
            'nik'=>(string)($reg['nik'] ?? $g['nik'] ?? ''),
            'name'=>(string)$g['name'],
            'total'=>count($g['services']),
            'area_label'=>$g['area_label'] ?: ($g['sto'] ?: '-'),
            'sto'=>$g['sto'],
        ];
    }
    usort($leaderboard,fn($a,$b)=>$b['total']<=>$a['total'] ?: strcmp(norm_name($a['name']),norm_name($b['name'])));

    $trend=[];
    if ($period === 'weekly') {
        // Exactly seven dates: Friday -> Thursday.
        $trendDates=[];
        for($d=$weekStart;$d <= $weekEnd;$d=$d->modify('+1 day')) $trendDates[]=$d;
    } else {
        $trendDates=[];
        for($i=6;$i>=0;$i--) $trendDates[]=$today->modify("-$i days");
    }
    foreach ($trendDates as $d) {
        $day=$d->format('Y-m-d');
        if ($hasReport) {
            $areaSql='1=1'; $areaParams=[];
            if($area==='JGR' || $area==='MYR'){
                $areaSql="EXISTS (SELECT 1 FROM report_area_orders ra WHERE ra.service_number=r.service_number AND ra.period_start=r.period_start AND UPPER(TRIM(ra.sto_code))=?)";
                $areaParams=[$area];
            }
            $ts=db()->prepare("SELECT r.service_number FROM report_group_orders r WHERE substr(r.message_date,1,10)=? AND {$areaSql}");
            $ts->execute(array_merge([$day],$areaParams));
            $seen=[]; foreach($ts->fetchAll() as $tr){$s=norm_key($tr['service_number']??'');if($s!=='')$seen[$s]=1;}
            $total=count($seen);
        } else {
            $total=0;
        }
        $trend[]=['date'=>$day,'label'=>DAYS_ID[((int)$d->format('N'))-1],'total'=>$total];
    }

    $total=array_sum(array_column($leaderboard,'total'));
    $active=count($leaderboard);

    $rca=load_rca_summary_php($area);
    $rca['period']=$period;
    $rca['period_label']=$label;

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
        'rca_summary'=>$rca,
        'backend'=>$hasReport?'php-report-history':'php-orders-fallback-no-history',
    ];
}
