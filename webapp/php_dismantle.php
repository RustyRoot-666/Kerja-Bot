<?php

declare(strict_types=1);

function ensure_dismantle_schema(): void {
    static $ready = false;
    if ($ready) return;
    db()->exec("CREATE TABLE IF NOT EXISTS dismantle_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        service_number TEXT NOT NULL UNIQUE,
        customer_name TEXT NOT NULL DEFAULT '',
        address TEXT NOT NULL DEFAULT '',
        customer_phone TEXT NOT NULL DEFAULT '',
        assigned_nik TEXT NOT NULL DEFAULT '',
        assigned_name TEXT NOT NULL DEFAULT '',
        assigned_username TEXT NOT NULL DEFAULT '',
        assigned_telegram_id INTEGER,
        source_chat_id INTEGER,
        source_message_id INTEGER,
        status TEXT NOT NULL DEFAULT 'OPEN',
        raw_source TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        completed_at TEXT
    )");
    db()->exec("CREATE INDEX IF NOT EXISTS idx_dismantle_assignee ON dismantle_orders(assigned_telegram_id, assigned_nik, status)");
    db()->exec("CREATE INDEX IF NOT EXISTS idx_dismantle_completed ON dismantle_orders(completed_at)");

    $seed = [
        ['152303278616','M****','MULYOREJO TENGAH 1 NO 26 SURABAYA Jalan Ngagel Surabaya 60246 Surabaya Indonesia','JAWA TIMUR'],
        ['152303277738','S****','Mulyorejo Tengah 1/30 Jalan Dokter Ir. Haji Soekarno Surabaya 60115 Surabaya Indonesia','JAWA TIMUR'],
        ['152303272481','B*******','Mulyorejo Tengah Gang V No. 14 Mulyorejo Tengah Gang V Surabaya 00000 Surabaya Indonesia','JAWA TIMUR'],
        ['152303271125','D****','Mulyorejo Tengah Gang V Surabaya','JAWA TIMUR'],
        ['152303272779','N****','mulyorejo tengah gg 1 no 16','JAWA TIMUR'],
        ['152303279918','M********','MULYOREJO TENGAH NO 51 SURABAYA','JAWA TIMUR'],
        ['152303277003','*****','MULYOREJO TENGAH NO.37','JAWA TIMUR'],
    ];
    $st = db()->prepare("INSERT OR IGNORE INTO dismantle_orders (
        service_number,customer_name,address,customer_phone,assigned_nik,assigned_name,assigned_username,
        status,raw_source,created_at,updated_at
    ) VALUES (?,?,?,?, '26050138','THOMAS GUSTIAN BAGYO','ThomasGustian','OPEN','SEED OSA MYR',datetime('now'),datetime('now'))");
    foreach ($seed as $row) $st->execute($row);
    $ready = true;
}

function dismantle_owned_where(array $tech): array {
    $telegramId = (int)($tech['telegram_id'] ?? 0);
    $nik = trim((string)($tech['nik'] ?? ''));
    return [
        '(assigned_telegram_id = ? OR (? <> \'\' AND TRIM(assigned_nik) = ?))',
        [$telegramId, $nik, $nik],
    ];
}

function dismantle_order_payload(array $row): array {
    return [
        'id' => (int)$row['id'],
        'service_number' => (string)$row['service_number'],
        'customer_name' => clean($row['customer_name'] ?? '') ?: '-',
        'address' => clean($row['address'] ?? '') ?: '-',
        'customer_phone' => clean($row['customer_phone'] ?? '') ?: '-',
        'assigned_nik' => clean($row['assigned_nik'] ?? ''),
        'assigned_name' => clean($row['assigned_name'] ?? '') ?: '-',
        'assigned_username' => clean($row['assigned_username'] ?? ''),
        'status' => norm($row['status'] ?? 'OPEN'),
        'created_at' => (string)($row['created_at'] ?? ''),
        'completed_at' => (string)($row['completed_at'] ?? ''),
    ];
}

function dismantle_trend(array $tech): array {
    [$where, $params] = dismantle_owned_where($tech);
    $today = new DateTimeImmutable('today');
    $items = [];
    for ($i = 6; $i >= 0; $i--) {
        $day = $today->modify("-$i days");
        $next = $day->modify('+1 day');
        $st = db()->prepare("SELECT COUNT(*) FROM dismantle_orders WHERE $where AND status='DONE' AND completed_at >= ? AND completed_at < ?");
        $st->execute([...$params, $day->format('Y-m-d H:i:s'), $next->format('Y-m-d H:i:s')]);
        $items[] = [
            'label' => DAYS_ID[(int)$day->format('N') - 1],
            'date' => $day->format('Y-m-d'),
            'total' => (int)$st->fetchColumn(),
        ];
    }
    return $items;
}

function load_dismantle_orders(int $telegramId): array {
    ensure_dismantle_schema();
    $tech = technician_by_telegram($telegramId);
    if (!$tech) return ['ok'=>false,'error'=>'technician_not_registered','message'=>'Akun Telegram belum terdaftar sebagai teknisi.'];
    [$where, $params] = dismantle_owned_where($tech);

    $st = db()->prepare("SELECT * FROM dismantle_orders WHERE $where ORDER BY CASE status WHEN 'OPEN' THEN 0 ELSE 1 END, address, service_number");
    $st->execute($params);
    $rows = $st->fetchAll();
    $open = [];
    $done = 0;
    foreach ($rows as $row) {
        if (norm($row['status'] ?? '') === 'DONE') $done++;
        else $open[] = dismantle_order_payload($row);
    }

    return [
        'ok' => true,
        'technician' => ['telegram_id'=>$telegramId,'nik'=>$tech['nik'],'name'=>$tech['name']],
        'open_count' => count($open),
        'done_count' => $done,
        'total_count' => count($rows),
        'orders' => $open,
        'trend' => dismantle_trend($tech),
    ];
}

function complete_dismantle_order(array $payload): array {
    ensure_dismantle_schema();
    $rawTelegram = trim((string)($payload['telegram_id'] ?? ''));
    $rawId = trim((string)($payload['id'] ?? ''));
    if (!ctype_digit($rawTelegram) || !ctype_digit($rawId)) return ['ok'=>false,'error'=>'invalid_request','message'=>'Data dismantle tidak valid.'];
    $telegramId = (int)$rawTelegram;
    $orderId = (int)$rawId;
    $tech = technician_by_telegram($telegramId);
    if (!$tech) return ['ok'=>false,'error'=>'technician_not_registered','message'=>'Teknisi tidak ditemukan.'];
    [$where, $params] = dismantle_owned_where($tech);

    $check = db()->prepare("SELECT id,status FROM dismantle_orders WHERE id=? AND $where LIMIT 1");
    $check->execute([$orderId, ...$params]);
    $row = $check->fetch();
    if (!$row) return ['ok'=>false,'error'=>'not_found','message'=>'Order dismantle tidak ditemukan.'];
    if (norm($row['status'] ?? '') === 'DONE') return ['ok'=>true,'already_done'=>true];

    $now = (new DateTimeImmutable('now'))->format('Y-m-d H:i:s');
    $st = db()->prepare("UPDATE dismantle_orders SET status='DONE', completed_at=?, updated_at=? WHERE id=?");
    $st->execute([$now, $now, $orderId]);
    return ['ok'=>true,'completed_at'=>$now];
}
