# Deploying on Windows Server 2022

This covers hosting Salesforce Nexus AI Server as a **native Windows container**
(process isolation) on Windows Server 2022, using `Dockerfile.windows` and
`docker-compose.windows.yml`. If you'd rather run the existing Linux image on
a Windows Server host via Hyper-V/WSL2 Linux containers, use the regular
`Dockerfile` and `docker-compose.yml` instead — nothing below applies to that
path.

## 1. Prerequisites on the host

Run these from an elevated PowerShell prompt on the Windows Server 2022 host.

**Install the Containers feature and reboot:**
```powershell
Install-WindowsFeature -Name Containers
Restart-Computer -Force
```

**Install Docker (Mirantis Container Runtime is Microsoft's supported engine
for Windows Server; Docker Desktop is not licensed for server use):**
```powershell
Install-Module DockerMsftProvider -Force
Install-Package Docker -ProviderName DockerMsftProvider -Force
Restart-Computer -Force
```

**Confirm Docker is running in Windows containers mode** (this is the default
on Windows Server — there is no Linux/Windows switch like on Docker Desktop):
```powershell
docker version
# Server: OS/Arch should read windows/amd64
```

**Confirm your host's build number**, since process-isolated containers
require the container base image's build to match:
```powershell
[System.Environment]::OSVersion.Version
# or:
Get-ComputerInfo | Select-Object WindowsVersion, OsBuildNumber
```
`Dockerfile.windows` uses `ltsc2022` base images (build 20348). If your host
has since been patched past that build and containers fail to start with an
isolation error, either apply the matching update inside your build process
or run with Hyper-V isolation (see step 4).

## 2. Get the project onto the host

Copy or `git clone` this project folder onto the Windows Server host — e.g.
into `C:\salesforce-nexus-ai-server\`.

> **Network note:** the build downloads Node.js directly from `nodejs.org` and
> the base images from `mcr.microsoft.com` and Docker Hub. If the build host
> sits behind a restrictive egress proxy/firewall, allow-list those domains
> (or point `Dockerfile.windows`'s Node.js download step at an internal
> mirror).

## 3. Configure environment

```powershell
cd C:\salesforce-nexus-ai-server
Copy-Item .env.example .env
notepad .env    # set SECRET_KEY at minimum
```

## 4. Build and run

```powershell
docker compose -f docker-compose.windows.yml up --build
```

This builds the React admin console (Node stage) and the Python backend
(both on Windows Server Core base images) into a single Windows container
image, and starts it with two named volumes for persistent SQLite/log
storage. Open **http://localhost:8000** (or the host's hostname/IP from
another machine, port 8000).

If you hit an isolation-mode error (container base image build doesn't match
the host build), edit `docker-compose.windows.yml` and uncomment:
```yaml
isolation: hyperv
```
then re-run `docker compose -f docker-compose.windows.yml up --build`.

To run without Compose:
```powershell
docker build -f Dockerfile.windows -t salesforce-nexus-ai-server:windows .
docker run -d --name nexus `
  -p 8000:8000 `
  -e SECRET_KEY=change_me `
  -v nexus-data:C:\app\data `
  -v nexus-logs:C:\app\logs `
  salesforce-nexus-ai-server:windows
```

## 5. Updating

After pulling new code:
```powershell
docker compose -f docker-compose.windows.yml up --build
```
The named volumes (`nexus-data`, `nexus-logs`) persist across rebuilds, so
your orgs, event configs, transactions, users, and DSSClient/processor
settings are untouched.

## Notes specific to the Windows image

- **Base images**: `mcr.microsoft.com/windows/servercore:ltsc2022` (build stage, with Node.js
  installed directly from the official nodejs.org release archive — there is no official
  Node.js image for Windows containers on Docker Hub, only Linux variants, so this avoids
  depending on an unofficial third-party Node-on-Windows image) and
  `python:3.12-windowsservercore-ltsc2022` (runtime, an official Microsoft/Python image). These
  are large (several GB) compared to the Linux `-slim` images — that's inherent to Windows
  Server Core containers, not something specific to this app.
- **uvicorn's optional speedups**: `uvicorn[standard]` normally pulls in
  `uvloop`/`httptools` for extra performance, but both are Unix-only and are
  automatically skipped by pip on Windows (they're gated by an upstream
  `sys_platform != 'win32'` marker) — no requirements.txt changes needed;
  uvicorn transparently falls back to its pure-Python event loop.
- **Volumes**: Compose's short volume syntax (`source:target`) breaks on
  Windows because a Windows path's drive-letter colon collides with
  Compose's own delimiter — `docker-compose.windows.yml` uses the explicit
  long-form volume syntax to avoid that.
- **This image has not been build-tested against a live Windows container
  runtime** (this project was assembled in a Linux-only sandbox with no
  Windows container host, and no access to Microsoft's or nodejs.org's
  download servers, available to it). The Linux `Dockerfile` *was* verified
  end to end by physically replicating its container filesystem layout and
  running the real app inside it; the same wasn't possible here. Please run
  a real `docker compose -f docker-compose.windows.yml up --build` on your
  Windows Server 2022 host before relying on this in production. If the
  Node.js download step needs a different version, override it with
  `--build-arg` or edit the `NODE_VERSION` line near the top of
  `Dockerfile.windows`, and let us know if anything else needs adjusting.
