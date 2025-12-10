Name:           geppetto_automation
Version:        0.0.5
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

%files -f %{pyproject_files}
%{_bindir}/geppetto-auto
%doc README.md
%license LICENSE

%changelog
* Wed Feb 12 2025 Geppetto Maintainers <noreply@example.invalid> - 0.1.0-1
- Initial package
