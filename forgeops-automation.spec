Name:           forgeops_automation
Version:        0.0.4
Release:        1%{?dist}
Summary:        ForgeOps automation tools

License:        MIT
URL:            https://example.invalid/forgeops-automation
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
Lightweight systems automation toolkit for ForgeOps.

%prep
%autosetup -n %{name}-%{version}

%build
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files forgeops_automation

%files -f %{pyproject_files}
%{_bindir}/forgeops-auto
%doc README.md
%license LICENSE

%changelog
* Wed Feb 12 2025 ForgeOps Maintainers <noreply@example.invalid> - 0.1.0-1
- Initial package
