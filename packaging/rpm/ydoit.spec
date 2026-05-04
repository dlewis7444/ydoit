Name:           ydoit
Version:        2.0.1
Release:        1%{?dist}
Summary:        Keyboard shortcut auto-typer for GNOME/Wayland

License:        MIT
URL:            https://github.com/dlewis7444/ydoit
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch

BuildRequires:  meson >= 0.62.0
BuildRequires:  python3-devel

Requires:       python3-gobject
Requires:       gtk4
Requires:       libadwaita
Requires:       libsecret
Requires:       gnupg2
Requires:       ydotool

%description
ydoit is a keyboard shortcut auto-typer for GNOME/Wayland. It stores encrypted
text entries and types them via ydotool when triggered by GNOME keyboard
shortcuts.

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

%changelog
* Tue Mar 10 2026 ydoit contributors - 2.0.0-1
- Initial RPM package
