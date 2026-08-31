<?php

declare(strict_types=1);

function dashboard_identity_clean_name(mixed $value): string {
    $x = strtoupper(trim((string)$value));
    $x = preg_replace('/^(?:NAME|NAMA)?\s*-?\s*\|\s*/i', '', $x) ?: $x;
    $x = preg_replace('/^(?:NAME|NAMA)\s*[-:=]\s*/i', '', $x) ?: $x;
    $x = preg_replace('/[^A-Z0-9]+/', ' ', $x) ?: $x;
    return trim(preg_replace('/\s+/', ' ', $x) ?: '');
}

function dashboard_identity_technicians(): array {
    if (!table_exists('technicians')) return [];
    try {
        $rows = db()->query("SELECT telegram_id, nik, name, sto FROM technicians WHERE TRIM(COALESCE(nik,''))<>''")->fetchAll();
    } catch (Throwable) {
        return [];
    }
    $out=[];
    foreach($rows as $row){
        $nik=preg_replace('/\D/','',(string)($row['nik']??''))?:'';
        $name=dashboard_identity_clean_name($row['name']??'');
        if($nik===''||$name==='')continue;
        $out[]=['nik'=>$nik,'name'=>$name,'sto'=>strtoupper(trim((string)($row['sto']??''))),'telegram_id'=>(int)($row['telegram_id']??0)];
    }
    return $out;
}

function dashboard_identity_match(string $name, array $technicians): ?array {
    $key=dashboard_identity_clean_name($name);
    if($key===''||$key==='-')return null;
    $matches=[];
    foreach($technicians as $t){
        $canonical=(string)$t['name'];
        if($canonical===$key || str_starts_with($canonical,$key.' ') || str_starts_with($key,$canonical.' ')) $matches[]=$t;
    }
    if(count($matches)!==1)return null;
    return $matches[0];
}

function dashboard_identity_fill_missing_nik(array $payload): array {
    if(!isset($payload['leaderboard'])||!is_array($payload['leaderboard']))return $payload;
    $techs=dashboard_identity_technicians();
    if(!$techs)return $payload;
    foreach($payload['leaderboard'] as &$row){
        $nik=preg_replace('/\D/','',(string)($row['nik']??''))?:'';
        if($nik!=='')continue;
        $match=dashboard_identity_match((string)($row['name']??''),$techs);
        if(!$match)continue;
        $row['nik']=$match['nik'];
        $row['name']=$match['name'];
        if(trim((string)($row['sto']??''))==='')$row['sto']=$match['sto'];
        $row['key']='NIK:'.$match['nik'];
    }
    unset($row);
    return $payload;
}
