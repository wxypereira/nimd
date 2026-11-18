# Maintainer: Ebert Silva <testenada53@gmail.com>
pkgname='nimd'
pkgver=2.0.0
pkgrel=1
pkgdesc="Conjunto de ferramentas para diagnóstico, tuning e benchmark de sistemas Linux (Arch/Manjaro/CachyOS)."
arch=('x86_64')
url="https://github.com/wxypereira/nimd"
license=('MIT')
groups=()
depends=('python' 'lm_sensors' 'dmidecode' 'util-linux' 'cpupower' 'stress-ng' 'bc' 'cronie' 'sysbench')
makedepends=('git')
provides=("${pkgname%-VCS}")
conflicts=("${pkgname%-VCS}")
replaces=()
backup=()
options=()
install=
source=('git+https://github.com/wxypereira/nimd.git')
noextract=()
sha256sums=('SKIP')

pkgver() {
  echo $pkgver
}

package() {
	cd "$srcdir/$pkgname"
  mkdir -p "$pkgdir/usr/local/bin"

  cp -r src/auditor "$pkgdir/usr/local/bin/auditor"
  cp -r scripts/* "$pkgdir/usr/local/bin"

  ln -s "$pkgdir/usr/local/bin/auditor/audit.py" "$pkgdir/usr/local/bin/audit"
}
