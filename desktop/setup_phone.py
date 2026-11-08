"""
Set up the Joey & Ryan phone app for your home Wi-Fi (one time).
Nothing to install on the phone, no accounts.

Run:  python setup_phone.py
"""

from joey_phone import PORT, SECURE_PORT, local_ip, make_config


def show_qr(url):
    try:
        import qrcode
        qr = qrcode.QRCode(border=1)
        qr.add_data(url)
        qr.make()
        print("\nScan this with your phone's camera:\n")
        qr.print_ascii(invert=True)
    except ImportError:
        print("\n(Tip: run  pip install qrcode  and then this again to get a QR code to scan.)")


def main():
    cfg = make_config()
    ip = local_ip()
    try:
        import joey_certs
        joey_certs.server_cert_for(ip)          # the PC's own security certificate (for the mic)
        has_cert = True
    except ImportError:
        print("For talking by voice on the phone, first run:  pip install cryptography   and then this again.\n")
        has_cert = False
    url = f"http://{ip}:{PORT}/{'mic-setup' if has_cert else ''}?key={cfg['key']}"
    print("Joey & Ryan phone app - home Wi-Fi\n")
    print("Open this on your phone (keep it private - it has your key):\n")
    print(f"   {url}\n")
    show_qr(url)
    print(f"""
Before it works:
  1. Restart Joey on this PC (it shows  [phone app ready at http://{ip}:{PORT}] ).
  2. Allow both phone-app doors through Windows Firewall (once). In PowerShell "Run as administrator":
       New-NetFirewallRule -DisplayName "Joey phone app" -Direction Inbound -Protocol TCP -LocalPort {PORT},{SECURE_PORT} -Action Allow -RemoteAddress LocalSubnet
     (only devices on your home network can reach it)
  3. Your phone must be on the SAME Wi-Fi as this PC.

On your phone:
  - Scan the QR code. It opens "Turn on voice": install the certificate once (it shows you how),
    then tap "Open Joey with voice" - from then on just tap the mic and talk.
  - iPhone: Share > Add to Home Screen.   Android: menu (3 dots) > Add to Home screen.

If it stops working one day, your PC's address may have changed: just run this again.""")


if __name__ == "__main__":
    main()
