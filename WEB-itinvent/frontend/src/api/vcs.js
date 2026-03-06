import apiClient from './client';

export const vcsAPI = {
    getComputers: async () => {
        const response = await apiClient.get('/vcs/computers');
        return response.data;
    },

    createComputer: async (data) => {
        const response = await apiClient.post('/vcs/computers', data);
        return response.data;
    },

    updateComputer: async (id, data) => {
        const response = await apiClient.put(`/vcs/computers/${id}`, data);
        return response.data;
    },

    deleteComputer: async (id) => {
        const response = await apiClient.delete(`/vcs/computers/${id}`);
        return response.data;
    },

    getConfig: async () => {
        const response = await apiClient.get('/vcs/config');
        return response.data;
    },

    updateConfig: async (configData) => {
        const response = await apiClient.put('/vcs/config', configData);
        return response.data;
    },

    getInfo: async () => {
        const response = await apiClient.get('/vcs/info');
        return response.data;
    },

    updateInfo: async (infoData) => {
        const response = await apiClient.put('/vcs/info', infoData);
        return response.data;
    },

    // Helper method to download fallback .vnc file
    downloadVncFile: (ipAddress, name, globalPasswordHex = '') => {
        const endpoint = String(ipAddress || '').trim();
        let host = endpoint;
        let port = '5900';
        const hostPortMatch = endpoint.match(/^(.*):(\d+)$/);
        if (hostPortMatch) {
            host = hostPortMatch[1];
            port = hostPortMatch[2];
        }

        const normalizedHex = String(globalPasswordHex || '').trim().toLowerCase();
        const lines = [
            '[connection]',
            'host=' + host,
            'port=' + port,
        ];
        if (/^[0-9a-f]{16}$/.test(normalizedHex)) {
            lines.push('password=' + normalizedHex);
        }
        lines.push(
            '',
            '[options]',
            'use_encoding_1=1',
            'copyrect=1',
            'viewonly=0',
            'fullscreen=0',
            '8bit=0',
            'shared=1',
            'belldeiconify=0',
            'disableclipboard=0',
            'swapmouse=0',
            'fitwindow=1',
            'cursorshape=1',
            'noremotecursor=0',
            'preferred_encoding=7',
            'compresslevel=-1',
            'quality=6',
            'localcursor=1',
            'scale_den=1',
            'scale_num=1',
            'local_cursor_shape=1'
        );
        const content = lines.join('\r\n') + '\r\n';
        const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.setAttribute('download', (name || host) + '.vnc');
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
    },

    // Downloads a single .bat installer that:
    // 1. Creates C:\ITInventVNC\ folder
    // 2. Writes vnc_handler.ps1 into it (via PowerShell, avoiding CMD escaping issues)
    // 3. Registers vnc:// protocol in HKCU registry
    // All fully automatic — user just runs the .bat once.
    downloadVncRegFile: () => {
        // The PowerShell script content is base64-encoded to avoid ALL escaping issues
        // when writing it from a .bat file.
        const ps1Script = [
            'param([string]$rawUri)',
            '$logPath = Join-Path $env:TEMP "vnc_debug.log"',
            'Add-Content $logPath ("[" + (Get-Date -Format "o") + "] STARTED")',
            '$uri = [System.Uri]::UnescapeDataString($rawUri).Trim(\'"\')',
            '$m = [regex]::Match($uri, \'(?i)^vnc://([^/?#]+)\')',
            'if (-not $m.Success) { Add-Content $logPath "Regex Match Failed"; exit }',
            '$endpoint = $m.Groups[1].Value.TrimEnd(\'/\')',
            '',
            '$query = \'\'',
            '$qm = [regex]::Match($uri, \'\\?(.*)$\')',
            'if ($qm.Success) { $query = $qm.Groups[1].Value }',
            '',
            '$passwordHex = \'\'',
            '$hm = [regex]::Match($query, \'(?:^|&)password_hex=([^&]+)\')',
            'if ($hm.Success) { $passwordHex = [System.Uri]::UnescapeDataString($hm.Groups[1].Value).Trim().ToLower() }',
            '',
            '$password = \'\'',
            '$pm = [regex]::Match($query, \'(?:^|&)password=([^&]+)\')',
            'if ($pm.Success) { $password = [System.Uri]::UnescapeDataString($pm.Groups[1].Value) }',
            '',
            '$viewer = \'C:\\Program Files\\TightVNC\\tvnviewer.exe\'',
            'if (-not (Test-Path $viewer)) { $viewer = \'C:\\Program Files (x86)\\TightVNC\\tvnviewer.exe\' }',
            'if (-not (Test-Path $viewer)) { Add-Content $logPath "No viewer found"; exit }',
            '',
            'if ($passwordHex -match \'^[0-9a-f]{16}$\') {',
            '    $h = $endpoint; $p = \'5900\'',
            '    if ($endpoint -match \'^(.+):(\\d+)$\') { $h = $Matches[1]; $p = $Matches[2] }',
            '    $tmp = Join-Path $env:TEMP (\'vnc_\' + [guid]::NewGuid().ToString() + \'.vnc\')',
            '    $lines = @(',
            '        "[connection]",',
            '        "host=$h",',
            '        "port=$p",',
            '        "password=$passwordHex",',
            '        "",',
            '        "[options]",',
            '        "use_encoding_1=1",',
            '        "copyrect=1",',
            '        "viewonly=0",',
            '        "fullscreen=0",',
            '        "8bit=0",',
            '        "shared=1",',
            '        "belldeiconify=0",',
            '        "disableclipboard=0",',
            '        "swapmouse=0",',
            '        "fitwindow=1",',
            '        "cursorshape=1",',
            '        "noremotecursor=0",',
            '        "preferred_encoding=7",',
            '        "compresslevel=-1",',
            '        "quality=6",',
            '        "localcursor=1",',
            '        "scale_den=1",',
            '        "scale_num=1",',
            '        "local_cursor_shape=1"',
            '    )',
            '    Set-Content -Path $tmp -Value $lines -Encoding Ascii',
            '    Add-Content $logPath ("LAUNCHING AUTOLOGIN: " + $tmp)',
            '    Start-Process -FilePath $viewer -ArgumentList "-optionsfile=`"$tmp`""',
            '    for ($i = 0; $i -lt 30; $i++) {',
            '        Start-Sleep -Milliseconds 500',
            '        try {',
            '            Remove-Item -LiteralPath $tmp -Force -ErrorAction Stop',
            '            Add-Content $logPath ("CLEANUP OK: " + $tmp)',
            '            break',
            '        } catch { }',
            '    }',
            '    if (Test-Path $tmp) { Add-Content $logPath ("CLEANUP SKIPPED: " + $tmp) }',
            '} elseif ($password) {',
            '    Add-Content $logPath ("LAUNCHING DIRECT: " + $endpoint + " with password")',
            '    Start-Process $viewer @($endpoint, \'-password\', $password)',
            '} else {',
            '    Add-Content $logPath ("LAUNCHING RAW: " + $endpoint)',
            '    Start-Process $viewer $endpoint',
            '}',
        ].join('\r\n');

        // Base64 encode the PS1 script for safe embedding in the .bat file
        // We encode as UTF-8 bytes then base64, and decode with certutil in the .bat
        const encoder = new TextEncoder();
        const ps1Bytes = encoder.encode(ps1Script);
        let binary = '';
        for (let i = 0; i < ps1Bytes.length; i++) {
            binary += String.fromCharCode(ps1Bytes[i]);
        }
        const ps1Base64 = btoa(binary);

        // Split base64 into lines of 76 chars for certutil compatibility
        const b64Lines = [];
        for (let i = 0; i < ps1Base64.length; i += 76) {
            b64Lines.push(ps1Base64.substring(i, i + 76));
        }

        // Build the .bat file content
        // Uses certutil to decode the base64 PS1 script — no echo escaping needed!
        const batLines = [
            '@echo off',
            'chcp 65001 >nul',
            'echo ========================================',
            'echo   IT-Invent VNC Protocol Installer',
            'echo ========================================',
            'echo.',
            '',
            'echo [1/3] Creating folder %LOCALAPPDATA%\\ITInventVNC\\...',
            'if not exist "%LOCALAPPDATA%\\ITInventVNC" mkdir "%LOCALAPPDATA%\\ITInventVNC"',
            '',
            'echo [2/3] Writing VNC handler script...',
            ':: Write base64-encoded PS1 script to temp file',
            'echo -----BEGIN CERTIFICATE----- > "%TEMP%\\vnc_ps1.b64"',
            ...b64Lines.map(line => 'echo ' + line + ' >> "%TEMP%\\vnc_ps1.b64"'),
            'echo -----END CERTIFICATE----- >> "%TEMP%\\vnc_ps1.b64"',
            ':: Decode base64 to actual PS1 file (force overwrite)',
            'certutil -f -decode "%TEMP%\\vnc_ps1.b64" "%LOCALAPPDATA%\\ITInventVNC\\vnc_handler.ps1" >nul 2>&1',
            'del "%TEMP%\\vnc_ps1.b64" >nul 2>&1',
            '',
            'echo [3/3] Registering VNC protocol...',
            'reg add "HKCU\\Software\\Classes\\vnc" /ve /t REG_SZ /d "URL:VNC Protocol" /f >nul',
            'reg add "HKCU\\Software\\Classes\\vnc" /v "URL Protocol" /t REG_SZ /d "" /f >nul',
            'reg add "HKCU\\Software\\Classes\\vnc\\shell\\open\\command" /ve /t REG_SZ /d "\"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe\" -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File \"%LOCALAPPDATA%\\ITInventVNC\\vnc_handler.ps1\" \"%%1\"" /f >nul',
            '',
            'echo.',
            'echo ========================================',
            'echo   Installation complete!',
            'echo   VNC protocol registered successfully.',
            'echo ========================================',
            'echo.',
            'pause',
        ];

        const batContent = batLines.join('\r\n') + '\r\n';
        const blob = new Blob([batContent], { type: 'text/plain;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.setAttribute('download', 'install_vnc_protocol.bat');
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
    }
};
