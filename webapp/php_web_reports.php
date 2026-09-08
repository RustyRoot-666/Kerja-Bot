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

function web_replacement_norm_inet(string $value): string {
    return preg_replace('/\D+/', '', trim($value));
}

function web_replacement_header_map(array $headers): array {
    $map=[];
    foreach($headers as $i=>$h) $map[norm($h)]=$i;
    return $map;
}

function web_replacement_col(array $map,array $aliases): ?int {
    foreach($aliases as $alias){$k=norm($alias);if(array_key_exists($k,$map))return$map[$k];}
    return null;
}

function web_replacement_status_data(): array {
    $report=[];
    if(table_exists('report_group_orders')){
        try{
            foreach(db()->query('SELECT service_number FROM report_group_orders')->fetchAll() as $r){
                $n=web_replacement_norm_inet((string)($r['service_number']??''));
                if($n!=='')$report[$n]=true;
            }
        }catch(Throwable $e){error_log('[miniapp-php] replacement report status unavailable: '.$e->getMessage());}
    }

    $updates=[];
    if(table_exists('kendala_updates')){
        try{
            $q=db()->query('SELECT service_number,status,rca,id FROM kendala_updates ORDER BY id ASC');
            foreach($q->fetchAll() as $r){
                $n=web_replacement_norm_inet((string)($r['service_number']??''));
                if($n==='')continue;
                if(!isset($updates[$n]))$updates[$n]=[];
                $updates[$n][]=[
                    'status'=>norm($r['status']??''),
                    'rca'=>norm($r['rca']??''),
                    'id'=>(int)($r['id']??0),
                ];
            }
        }catch(Throwable $e){error_log('[miniapp-php] replacement update status unavailable: '.$e->getMessage());}
    }
    return [$report,$updates];
}

function web_replacement_rows(): array {
    static $cache=null;
    if($cache!==null)return$cache;

    $raw=@file_get_contents(sheet_csv_url());
    if($raw===false||trim($raw)==='')throw new RuntimeException('Google Sheets tidak dapat dibaca.');
    $fp=fopen('php://temp','r+');fwrite($fp,preg_replace('/^\xEF\xBB\xBF/','',$raw));rewind($fp);
    $rows=[];while(($r=fgetcsv($fp))!==false)$rows[]=$r;fclose($fp);
    if(!$rows)throw new RuntimeException('Google Sheet kosong.');

    $headerIndex=-1;
    foreach(array_slice($rows,0,30,true) as $i=>$r){$m=web_replacement_header_map($r);if(web_replacement_col($m,['INET','NO INET','NO INTERNET','NO SERVICE'])!==null&&web_replacement_col($m,['TIM'])!==null){$headerIndex=$i;break;}}
    if($headerIndex<0)throw new RuntimeException('Kolom INET/TIM tidak ditemukan di Google Sheet.');

    $headers=$rows[$headerIndex];$map=web_replacement_header_map($headers);
    $inetCol=web_replacement_col($map,['INET','NO INET','NO INTERNET','NO SERVICE']);
    $timCol=web_replacement_col($map,['TIM']);
    $nameCol=web_replacement_col($map,['NAMA PETUGAS','PETUGAS','TEKNISI','NAMA TEKNISI']);
    $dateCol=web_replacement_col($map,['TANGGAL','DATE','TGL']);
    $ticketCol=web_replacement_col($map,['TICKET','TIKET']);
    $addressCol=web_replacement_col($map,['ALAMAT']);
    $customerCol=web_replacement_col($map,['NAMA']);
    $phoneCol=web_replacement_col($map,['CP','NO HP','NOMOR HP']);
    $rcaSheetCol=web_replacement_col($map,['RCA']);

    [$report,$updates]=web_replacement_status_data();
    $out=[];
    foreach(array_slice($rows,$headerIndex+1) as $row){
        $inet=web_replacement_norm_inet((string)($row[$inetCol]??''));
        $tim=norm($row[$timCol]??'');
        if($inet===''||$tim!=='REPLACEMENT')continue;

        $status='OPEN';$rca='';$latestUpdate=null;
        if(isset($report[$inet])){
            $status='CLOSE';$rca='DONE';
        }else{
            foreach(($updates[$inet]??[]) as $u){
                $s=(string)$u['status'];
                if(str_contains($s,'MENOLAK')||str_contains($s,'REJECT')||$s==='DITOLAK'){
                    $latestUpdate=['status'=>'MENOLAK','rca'=>(string)$u['rca'],'id'=>(int)$u['id'];
                }elseif($s==='UPDATE'||str_contains($s,'UPDATE')||str_contains($s,'PROGRESS')){
                    $latestUpdate=['status'=>'UPDATE','rca'=>(string)$u['rca'],'id'=>(int)$u['id'];
                }
            }
            if($latestUpdate){$status=$latestUpdate['status'];$rca=$latestUpdate['rca'];}
        }

        $out[]=[
            'service_number'=>$inet,
            'status'=>$status,
            'result'=>$status,
            'rca'=>$rca,
            'sheet_rca'=>norm($row[$rcaSheetCol]??''),
            'technician_name'=>trim((string)($row[$nameCol]??'')),
            'date'=>trim((string)($row[$dateCol]??'')),
            'raw_day'=>substr(trim((string)($row[$dateCol]??'')),0,10),
            'ticket_id'=>trim((string)($row[$ticketCol]??'')),
            'address'=>trim((string)($row[$addressCol]??'')),
            'customer_name'=>trim((string)($row[$customerCol]??'')),
            'customer_phone'=>trim((string)($row[$phoneCol]??'')),
            'source'=>'replacement_sheet',
        ];
    }

    $cache=$out;
    return$out;
}

function web_replacement_technician_matches(array $order,array $tech): bool {
    $sheetName=norm_name((string)($order['technician_name']??''));
    if($sheetName==='')return false;
    $techName=norm_name((string)($tech['name']??''));
    if($sheetName!==''&&$sheetName===$techName)return true;
    try{
        if(function_exists('technician_master_resolve')){
            $master=technician_master_resolve('',(string)($order['technician_name']??''));
            if($master&&norm_name((string)($master['canonical_name']??''))===$techName)return true;
        }
    }catch(Throwable $e){}
    return false;
}

function web_replacement_orders_for_tech(array $tech,string $area,string $period): array {
    if(!web_report_area_match((string)$tech['sto'],$area))return [];
    $orders=[];
    foreach(web_replacement_rows() as $o){
        if(!web_replacement_technician_matches($o,$tech))continue;
        if(!web_report_day_match((string)($o['raw_day']??''),$period))continue;
        $o['technician_nik']=$tech['nik'];$o['technician_name']=$tech['name'];$o['sto']=$tech['sto'];
        $orders[]=$o;
    }
    return$orders;
}

function web_report_technician_list(string $area,string $period): array {
    $out=[];
    try{$replacement=web_replacement_rows();}catch(Throwable $e){error_log('[miniapp-php] replacement report unavailable: '.$e->getMessage());$replacement=[];}
    foreach(report_filter_technicians() as $tech){
        if(!web_report_area_match((string)$tech['sto'],$area))continue;
        $orders=[];
        foreach($replacement as $o){if(web_replacement_technician_matches($o,$tech)&&web_report_day_match((string)($o['raw_day']??''),$period)){$o['technician_nik']=$tech['nik'];$o['technician_name']=$tech['name'];$o['sto']=$tech['sto'];$orders[]=$o;}}
        $counts=['close'=>0,'open'=>0,'update'=>0,'reject'=>0];
        foreach($orders as $o){$b=web_report_bucket(web_report_status($o));$counts[$b]++;}
        $out[]=['nik'=>$tech['nik'],'name'=>$tech['name'],'sto'=>$tech['sto'],'telegram_id'=>(int)($tech['telegram_id']??0),'total'=>count($orders),'close'=>$counts['close'],'open'=>$counts['open'],'update'=>$counts['update'],'menolak'=>$counts['reject'],'progress'=>count($orders)?round($counts['close']*100/count($orders),1):0];
    }
    usort($out,fn($a,$b)=>((int)$b['total']<=>(int)$a['total'])?:strcmp($a['name'],$b['name']));
    return$out;
}

function web_report_selected(int $viewerTelegramId,string $nik,string $area,string $period): array {
    $viewer=technician_by_telegram($viewerTelegramId);
    if(!$viewer || !report_is_supervisor($viewer))return['ok'=>false,'error'=>'forbidden','message'=>'Laporan teknisi lain hanya untuk supervisor/admin.'];
    $tech=report_target_by_nik($nik);
    if(!$tech)return['ok'=>false,'error'=>'technician_not_found','message'=>'Teknisi tidak ditemukan.'];
    if(!web_report_area_match((string)$tech['sto'],$area))return['ok'=>false,'error'=>'area_mismatch','message'=>'Teknisi tidak termasuk area filter.'];
    $tid=(int)($tech['telegram_id']??0);if($tid<=0)return['ok'=>false,'error'=>'technician_not_linked','message'=>'Teknisi belum terhubung ke akun Telegram.'];
    try{$orders=web_replacement_orders_for_tech($tech,$area,$period);}catch(Throwable $e){return['ok'=>false,'error'=>'replacement_source_error','message'=>$e->getMessage()];}
    $counts=['close'=>0,'open'=>0,'update'=>0,'reject'=>0];
    foreach($orders as &$o){$o['status']=web_report_status($o);$b=web_report_bucket($o['status']);$counts[$b]++;$o['date']=substr((string)($o['raw_day']??''),0,10);$o['technician_nik']=$tech['nik'];$o['technician_name']=$tech['name'];}unset($o);
    usort($orders,fn($a,$b)=>strcmp((string)$b['date'],(string)$a['date']?:strcmp((string)$a['service_number'],(string)$b['service_number']));
    return['ok'=>true,'technician'=>['nik'=>$tech['nik'],'name'=>$tech['name'],'sto'=>$tech['sto'],'telegram_id'=>$tid],'period'=>$period,'area'=>strtoupper($area),'summary'=>['total'=>count($orders),'close'=>$counts['close'],'open'=>$counts['open'],'update'=>$counts['update'],'menolak'=>$counts['reject'],'progress'=>count($orders)?round($counts['close']*100/count($orders),1):0],'orders'=>$orders];
}

function web_report_sheet_rows(): array {
    $raw=@file_get_contents(sheet_csv_url());if($raw===false||trim($raw)==='')throw new RuntimeException('Google Sheets tidak dapat dibaca.');
    $fp=fopen('php://temp','r+');fwrite($fp,preg_replace('/^\xEF\xBB\xBF/','',$raw));rewind($fp);$rows=[];while(($r=fgetcsv($fp))!==false)$rows[]=$r;fclose($fp);
    $norms=fn($v)=>norm($v);$serviceAliases=['NO INET','NO INTERNET','NO SERVICE','SERVICE NUMBER','INTERNET NUMBER','INET'];$headerIndex=-1;$serviceCol=null;
    foreach(array_slice($rows,0,30,true) as $i=>$r){foreach($r as $j=>$h){if(in_array($norms($h),$serviceAliases,true)){$serviceCol=$j;break;}}if($serviceCol!==null){$headerIndex=$i;break;}}
    if($headerIndex<0)throw new RuntimeException('Kolom INET tidak ditemukan di Google Sheet.');
    return['headers'=>$rows[$headerIndex],'rows'=>array_slice($rows,$headerIndex+1),'service_col'=>$serviceCol];
}

function web_report_export_rows(int $viewerTelegramId,string $nik,string $area,string $period): array {
    $selected=web_report_selected($viewerTelegramId,$nik,$area,$period);if(!($selected['ok']??false))return$selected;
    $keys=[];foreach($selected['orders'] as $o){$k=norm_key($o['service_number']??'');if($k!=='')$keys[$k]=true;}
    $sheet=web_report_sheet_rows();$out=[];
    foreach($sheet['rows'] as $row){$service=(string)($row[$sheet['service_col']]??'');$k=norm_key($service);if($k!==''&&isset($keys[$k]))$out[]=$row;}
    return['ok'=>true,'headers'=>$sheet['headers'],'rows'=>$out,'technician'=>$selected['technician'],'period'=>$period,'area'=>strtoupper($area),'matched'=>count($out),'reported'=>count($selected['orders'])];
}

function web_report_xml(string $v): string {return htmlspecialchars($v,ENT_QUOTES|ENT_XML1,'UTF-8');}
function web_report_excel(array $headers,array $rows): string {
    $xml='<?xml version="1.0" encoding="UTF-8"?><?mso-application progid="Excel.Sheet"?>';
    $xml.='<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet" xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:x="urn:schemas-microsoft-com:office:excel" xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet"><Worksheet ss:Name="Laporan"><Table>';
    $all=array_merge([$headers],$rows);foreach($all as $r){$xml.='<Row>';foreach($r as $v)$xml.='<Cell><Data ss:Type="String">'.web_report_xml((string)$v).'</Data></Cell>';$xml.='</Row>';}
    return$xml.'</Table></Worksheet></Workbook>';
}
