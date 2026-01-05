Name:           geppetto_automation
Version:        0.0.6
Release:        1%{?dist}
Summary:        Geppetto automation tools

License:        MIT
URL:            https://example.invalid/geppetto-automation
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch

BuildRequires:  python3-devel
BuildRequires:  python3-rpm-macros
BuildRequires:  python3dist(hatchling)
BuildRequires:  python3dist(tomli)
Requires:       python3 >= 3.9
Requires:       python3dist(jinja2) >= 2.11
Requires:       python3dist(boto3) >= 1.34
Requires:       python3dist(tomli)

%description
Lightweight systems automation toolkit for Geppetto.

%prep
%autosetup -n %{name}-%{version}

%build
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files geppetto_automation

# Sample config tree under /etc/geppetto
install -d %{buildroot}%{_sysconfdir}/geppetto/config/{defaults,groups/staging,hosts/host1,templates}
install -m 0644 examples/plan.fops %{buildroot}%{_sysconfdir}/geppetto/plan.fops.sample
install -m 0644 examples/config/main.conf.sample %{buildroot}%{_sysconfdir}/geppetto/main.conf.sample
install -m 0644 examples/config/defaults/*.fops %{buildroot}%{_sysconfdir}/geppetto/config/defaults/
install -m 0644 examples/config/groups/staging/*.fops %{buildroot}%{_sysconfdir}/geppetto/config/groups/staging/
install -m 0644 examples/config/hosts/host1/*.fops %{buildroot}%{_sysconfdir}/geppetto/config/hosts/host1/
install -m 0644 examples/config/templates/motd.tmpl %{buildroot}%{_sysconfdir}/geppetto/config/templates/motd.tmpl

%files -f %{pyproject_files}
%{_bindir}/geppetto-auto
%dir %{_sysconfdir}/geppetto
%dir %{_sysconfdir}/geppetto/config
%dir %{_sysconfdir}/geppetto/config/defaults
%dir %{_sysconfdir}/geppetto/config/groups
%dir %{_sysconfdir}/geppetto/config/groups/staging
%dir %{_sysconfdir}/geppetto/config/hosts
%dir %{_sysconfdir}/geppetto/config/hosts/host1
%dir %{_sysconfdir}/geppetto/config/templates
%config(noreplace) %{_sysconfdir}/geppetto/plan.fops.sample
%config(noreplace) %{_sysconfdir}/geppetto/main.conf.sample
%config(noreplace) %{_sysconfdir}/geppetto/config/defaults/*.fops
%config(noreplace) %{_sysconfdir}/geppetto/config/groups/staging/*.fops
%config(noreplace) %{_sysconfdir}/geppetto/config/hosts/host1/*.fops
%config(noreplace) %{_sysconfdir}/geppetto/config/templates/motd.tmpl
%doc README.md
%license LICENSE

%changelog
* Wed Feb 12 2025 Geppetto Maintainers <noreply@example.invalid> - 0.1.0-1
- Initial package
