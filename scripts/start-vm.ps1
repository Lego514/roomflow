$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$qemuExe = Join-Path $taskRoot '.runtime\qemu\qemu-system-x86_64.exe'
$kernelFile = Join-Path $taskRoot '.runtime\alpine-boot\boot\vmlinuz-virt'
$initrdFile = Join-Path $taskRoot '.runtime\alpine-boot\boot\initramfs-virt'
$isoFile = Join-Path $taskRoot '.runtime\downloads\alpine.iso'
foreach ($file in @($qemuExe,$kernelFile,$initrdFile,$isoFile)) {
  if (!(Test-Path -LiteralPath $file)) { throw "Required VM file missing: $file" }
}
$vmArgs = @('-m','1024','-smp','2','-accel','tcg','-display','none','-monitor','none',
  '-serial','tcp:127.0.0.1:4546,server=on,wait=off',
  '-kernel',('"'+$kernelFile+'"'),'-initrd',('"'+$initrdFile+'"'),
  '-append','"console=ttyS0 modules=loop,squashfs,sd-mod,usb-storage"',
  '-cdrom',('"'+$isoFile+'"'),'-netdev','user,id=n1','-device','virtio-net-pci,netdev=n1')
$vmProcess = Start-Process -FilePath $qemuExe -ArgumentList $vmArgs -WindowStyle Hidden -PassThru -WorkingDirectory $taskRoot -RedirectStandardError (Join-Path $taskRoot '.runtime\qemu-error.log') -RedirectStandardOutput (Join-Path $taskRoot '.runtime\qemu-output.log')
$vmProcess.Id | Set-Content -LiteralPath (Join-Path $taskRoot '.runtime\qemu.pid')
Write-Output ('Project VM PID ' + $vmProcess.Id)
