# 🔑 Your Jetson's public SSH key
$jetsonPublicKey = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQCdcOnL2PQ9Gz+zfaEYIF5rpDstdL4r9/7zAf8l3QV8hPhhzH6f2HDE3xK5NivzZ0rzJSeMXVucjeyTBDr6myKKz3SIrfW9e5Q8+G+oa1t74EexwFwV2IiY3NFBU0UaeoTenAixKoZxrD+mSWN6dI0do0CTH5rZ4PDQjScPOsp8jFg39n7smGxOw3GKgOkrP3NPV6PWRSRR1fA3EIjFALtsH3h4dD1yY8JJH10xoJhq+sBw/f1rSUG/AZkXIYXyqs+a+jmqNPqBDke2zzjxRMy53oiq4+Fwjmo7mO35uuM6zJ8/BrFNhMUbEIxDX6z/Pd8TclF7WbSd4Dbrlkp7hRgWsbnwiLm1h8rNi1BKz/bUj8DBcbT1T83E2o/sbVVpdorQgRuG3o/DVh9TZwBGXqQxUhyWm5gkAaAzKsCIYKNUF4/281Gw1Kp5vRQwemaqi4XaeD9A/YVW2etvz9Fpl+xQ56ObRnTkDojFaRf7+V9ZgF83caepHMYRnxfdHNFZWVXDolJuBrlZlhOZQX/7ri/i9vqDlcAt8O7sSojGEjdmxDouNteh8qDa/5fnXXpWrBtUai3xeQozfbeb9mDq7ZlECF5DkErCfg/zLGHuChviJbrO2cpnsrJSw/RKiK1ENQMG6HVLoOXhggdXtS6gnBs4yoKo2CFu3uJIMfOCw0GHmw== itouchedlogourt@itouchedlogurt-desktop"

$sshDir = "$env:USERPROFILE\.ssh"
$authorizedKeys = "$sshDir\authorized_keys"
$sshdConfig = "$env:ProgramData\ssh\sshd_config"

Write-Host "🔧 Setting up SSH key login for $env:USERNAME..."
Write-Host "📁 SSH directory: $sshDir"
Write-Host "📄 authorized_keys: $authorizedKeys"

# Create .ssh directory if it doesn't exist
if (!(Test-Path $sshDir)) {
    New-Item -ItemType Directory -Path $sshDir
    Write-Host "✅ Created .ssh directory"
}

# Add Jetson key to authorized_keys
if (Test-Path $authorizedKeys) {
    $existing = Get-Content $authorizedKeys
    if ($existing -notcontains $jetsonPublicKey) {
        Add-Content -Path $authorizedKeys -Value $jetsonPublicKey
        Write-Host "✅ Appended Jetson public key to authorized_keys"
    } else {
        Write-Host "ℹ️ Key already present in authorized_keys"
    }
} else {
    Set-Content -Path $authorizedKeys -Value $jetsonPublicKey
    Write-Host "✅ Created authorized_keys with Jetson key"
}

# Set correct permissions
Write-Host "🔐 Fixing file permissions..."
icacls $sshDir /inheritance:r /grant:r "$env:USERNAME:(OI)(CI)F"
icacls $authorizedKeys /inheritance:r /grant:r "$env:USERNAME:F"

# Ensure sshd_config is configured to allow keys
if (Test-Path $sshdConfig) {
    $config = Get-Content $sshdConfig
    $changesMade = $false

    if ($config -notmatch "PubkeyAuthentication yes") {
        Write-Host "🔧 Adding 'PubkeyAuthentication yes'"
        Add-Content $sshdConfig "`nPubkeyAuthentication yes"
        $changesMade = $true
    }

    if ($config -notmatch "AuthorizedKeysFile") {
        Write-Host "🔧 Adding 'AuthorizedKeysFile .ssh/authorized_keys'"
        Add-Content $sshdConfig "`nAuthorizedKeysFile .ssh/authorized_keys"
        $changesMade = $true
    }

    if ($changesMade) {
        Write-Host "🔄 Restarting SSH service..."
        Restart-Service sshd
    } else {
        Write-Host "✅ sshd_config already configured"
    }
} else {
    Write-Host "❌ sshd_config not found at $sshdConfig"
}

Write-Host "🎉 Done! Test from Jetson: ssh giova@192.168.1.97 (no password expected)"