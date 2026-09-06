<?php
declare(strict_types=1);

function web_report_day_match(string $day,string $period): bool {
    $day=substr(trim($day),0,10); if($day==='') return false;
    $period=strtolower(trim($period));
    if($period==='all') return true;
    $today=new DateTimeImmutable('today');
    if($period==='daily') return $day===$today->format('Y-m-d');
    [$start,$end]=period_bounds($today);
    return $day>=$start->format('Y-m-d') && $day<=$end->format('Y-m-d');
}

function web_report_area_match(string $sto,string $area): bool {
    $area=strtoupper(trim($area)); $sto=strtoupper(trim($sto));
    return $area==='ALL' || $area==='' || $sto===$area;
}

function web_report_status(array $o): string {
    return norm($o['result']??$o['status']??$o['hasil']??'');
}

function web_report_bucket(string $status): string {
    if(in_array($status,CLOSED_STATUSES,true)||str_contains($status,'CLOSE')||in_array($status,['DONE','SELESAI','COMPLETED'],true)) return 'close';
    if(in_array($status,UPDATE_STATUSES,true)||str_contains($status,'UPDATE')||str_contains($status,'PROGRESS')) return 'update';
    if(in_array($status,['MENOLAK','REJECT','REJECTED','DITOLAK'],true)||str_contains($status,'MENOLAK')||str_contains($status,'REJECT')) return 'reject';
    return 'open';
}

function web_report_technician_list(string $area,string $period): array {
    $out=[];
    foreach(report_filter_technicians() as $tech){
        if(!web_report_area_match((string)$tech['sto'],$area)) continue;
        $tid=(int)($tech['telegram_id']??0); $orders=[];
        if($tid>0){$p=load_my_report_php($tid);if(($p['ok']??false))$orders=$p['orders']??[];}
        $filtered=[];$counts=['close'=>0,'open'=>0,'update'=>0,'reject'=>0];
        foreach($orders as $o){$day=substr((string)($o['raw_day']??''),0,10);if(!web_report_day_match($day,$period))continue;$filtered[]=$o;$b=web_report_bucket(web_report_status($o));$counts[$b]++;}
        $out[]=['nik'=>$tech['nik'],'name'=>$tech['name'],'sto'=>$tech['sto'],'telegram_id'=>$tid,'total'=>count($filtered),'close'=>$counts['close'],'open'=>$counts['open'],'update'=>$counts['update'],'menolak'=>$counts['reject'],'progress'=>count($filtered)?round($counts['close']*100/count($filtered),1):0];
    }
    usort($out,fn($a,$b)=>((int)$b['total']<=>(int)$a['total'])?:strcmp($a['name'],$b['name']));
    return $out;
}

function web_report_selected(int $viewerTelegramId,string $nik,string $area,string $period): array {
    $viewer=technician_by_telegram($viewerTelegramId);
    if(!$viewer || !report_is_supervisor($viewer)) return ['ok'=>false,'error'=>'forbidden','message'=>'Laporan teknisi lain hanya untuk supervisor/admin.'];
    $tech=report_target_by_nik($nik);
    if(!$tech) return ['ok'=>false,'error'=>'technician_not_found','message'=>'Teknisi tidak ditemukan.'];
    if(!web_report_area_match((string)$tech['sto'],$area)) return ['ok'=>false,'error'=>'area_mismatch','message'=>'Teknisi tidak termasuk area filter.'];
    $tid=(int)($tech['telegram_id']??0); if($tid<=0) return ['ok'=>false,'error'=>'technician_not_linked','message'=>'Teknisi belum terhubung ke akun Telegram.'];
    $p=load_my_report_php($tid); if(!($p['ok']??false)) return $p;
    $orders=[];$counts=['close'=>0,'open'=>0,'update'=>0,'reject'=>0];
    foreach(($p['orders']??[]) as $o){$day=substr((string)($o['raw_day']??''),0,10);if(!web_report_day_match($day,$period))continue;$b=web_report_bucket(web_report_status($o));$counts[$b]++;$o['status']=web_report_status($o);$o['date']=$day;$o['technician_nik']=$tech['nik'];$o['technician_name']=$tech['name'];$orders[]=$o;}
    usort($orders,fn($a,$b)=>strcmp((string)$b['date'],(string)$a['date'])?:strcmp((string)$a['service_number'],(string)$b['service_number']));
    return ['ok'=>true,'technician'=>['nik'=>$tech['nik'],'name'=>$tech['name'],'sto'=>$tech['sto'],'telegram_id'=>$tid],'period'=>$period,'area'=>strtoupper($area),'summary'=>['total'=>count($orders),'close'=>$counts['close'],'open'=>$counts['open'],'update'=>$counts['update'],'menolak'=>$counts['reject'],'progress'=>count($orders)?round($counts['close']*100/count($orders),1):0],'orders'=>$orders];
}

function web_report_sheet_rows(): array {
    $raw=@file_get_contents(sheet_csv_url()); if($raw===false||trim($raw)==='') throw new RuntimeException('Google Sheets tidak dapat dibaca.');
    $fp=fopen('php://temp','r+');fwrite($fp,preg_replace('/^\xEF\xBB\xBF/','',$raw));rewind($fp);$rows=[];while(($r=fgetcsv($fp))!==false)$rows[]=$r;fclose($fp);
    $norms=fn($v)=>norm($v);$serviceAliases=['NO INET','NO INTERNET','NO SERVICE','SERVICE NUMBER','INTERNET NUMBER','INET'];$headerIndex=-1;$serviceCol=null;
    foreach(array_slice($rows,0,30,true) as $i=>$r){foreach($r as $j=>$h){if(in_array($norms($h),$serviceAliases,true)){$serviceCol=$j;break;}}if($serviceCol!==null){$headerIndex=$i;break;}}
    if($headerIndex<0)throw new RuntimeException('Kolom INET tidak ditemukan di Google Sheet.');
    return ['headers'=>$rows[$headerIndex],'rows'=>array_slice($rows,$headerIndex+1),'service_col'=>$serviceCol];
}

function web_report_export_rows(int $viewerTelegramId,string $nik,string $area,string $period): array {
    $selected=web_report_selected($viewerTelegramId,$nik,$area,$period);if(!($selected['ok']??false))return$selected;
    $keys=[];foreach($selected['orders'] as $o){$k=norm_key($o['service_number']??'');if($k!=='')$keys[$k]=true;}
    $sheet=web_report_sheet_rows();$out=[];
    foreach($sheet['rows'] as $row){$service=(string)($row[$sheet['service_col']]??'');$k=norm_key($service);if($k!==''&&isset($keys[$k]))$out[]=$row;}
    return ['ok'=>true,'headers'=>$sheet['headers'],'rows'=>$out,'technician'=>$selected['technician'],'period'=>$period,'area'=>strtoupper($area),'matched'=>count($out),'reported'=>count($selected['orders'])];
}

function web_report_xml(string $v): string {return htmlspecialchars($v,ENT_QUOTES|ENT_XML1,'UTF-8');}
function web_report_excel(array $headers,array $rows): string {
    $xml='<?xml version="1.0" encoding="UTF-8"?><?mso-application progid="Excel.Sheet"?>';
    $xml.='<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet" xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:x="urn:schemas-microsoft-com:office:excel" xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet"><Worksheet ss:Name="Laporan"><Table>';
    $all=array_merge([$headers],$rows);foreach($all as $r){$xml.='<Row>';foreach($r as $v)$xml.='<Cell><Data ss:Type="String">'.web_report_xml((string)$v).'</Data></Cell>';$xml.='</Row>';}
    return $xml.'</Table></Worksheet></Workbook>';
}
