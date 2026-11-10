module github.com/tarana/gnmic-agent

go 1.26.0

require (
	github.com/carlmjohnson/requests v0.25.1
	github.com/google/go-querystring v1.1.0
	github.com/sirupsen/logrus v1.9.3
	gopkg.in/yaml.v3 v3.0.1
)

require (
	// CVE-2026-25681, CVE-2026-33814, CVE-2026-46600, CVE-2026-78661, CVE-2026-78669: vulnerable version was v0.38.0; v0.62.0 chosen as the highest fixed version across all five CVEs.
	golang.org/x/net v0.62.0 // indirect
	golang.org/x/sys v0.49.0 // indirect
)
