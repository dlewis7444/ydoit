Name:           ydoit
Version:        2.2.0
Release:        1%{?dist}
Summary:        Keyboard shortcut auto-typer for GNOME/Wayland

License:        MIT
URL:            https://github.com/dlewis7444/ydoit
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch

BuildRequires:  meson >= 0.62.0
BuildRequires:  python3-devel
BuildRequires:  systemd-rpm-macros

Requires:       python3-gobject
Requires:       python3-dbus
Requires:       gtk4
Requires:       libadwaita
Requires:       libsecret
Requires:       gnupg2
Requires:       ydotool
Requires:       systemd

%description
ydoit is a keyboard shortcut auto-typer for GNOME/Wayland. It stores encrypted
text entries and types them via ydotool or Mutter RemoteDesktop when triggered
by GNOME keyboard shortcuts.

%prep
%autosetup

%build
%meson
%meson_build

%install
%meson_install

%post
gtk-update-icon-cache %{_datadir}/icons/hicolor &>/dev/null || :
update-desktop-database %{_datadir}/applications &>/dev/null || :
# Enable the user-scoped ydotoold unit for all users on next login.
systemctl --global enable ydotoold.service &>/dev/null || :

%preun
if [ $1 -eq 0 ]; then
    # Full removal (not upgrade): disable the global user unit.
    systemctl --global disable ydotoold.service &>/dev/null || :
fi

%postun
gtk-update-icon-cache %{_datadir}/icons/hicolor &>/dev/null || :
update-desktop-database %{_datadir}/applications &>/dev/null || :

%files
%license LICENSE
%{_bindir}/ydoit
%{_bindir}/ydoit-gui
%{python3_sitelib}/ydoit/
%{_datadir}/applications/org.ydoit.app.desktop
%{_datadir}/metainfo/org.ydoit.app.metainfo.xml
%{_datadir}/icons/hicolor/scalable/apps/org.ydoit.app.svg
%{_datadir}/icons/hicolor/symbolic/apps/org.ydoit.app-symbolic.svg
%{_prefix}/lib/systemd/user/ydotoold.service

%changelog
* Sun Jul 12 2026 David Lewis <david@lewisit.com> - 2.2.0-1
- Selectable input backend: auto / Mutter RemoteDesktop / ydotool
- GNOME Remote Desktop sessions type via Mutter (uinput is orphaned there)
- Manager Settings combo, ydoit type --backend, YDOIT_INPUT_BACKEND
- status reports configured vs effective backend

* Mon May 04 2026 David Lewis <david@lewisit.com> - 2.1.0-1
- Ship a user-scoped ydotoold systemd unit and enable it globally on install
- Probe the daemon socket directly (status now reflects reachability, not just process)
- Auto-start ydotoold via `systemctl --user` on first type if it isn't running
- Surface ydotool stdout in error messages (it writes connection errors there)

* Tue Mar 10 2026 ydoit contributors - 2.0.0-1
- Initial RPM package
