{{- define "app.labels" -}}
app.kubernetes.io/name: {{ .name }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/part-of: {{ .root.Chart.Name }}
app.kubernetes.io/version: {{ .root.Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .root.Release.Service }}
{{- end }}

{{- define "app.selector" -}}
app.kubernetes.io/name: {{ .name }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
{{- end }}

{{- define "app.image" -}}
{{- if .digest -}}{{ .repository }}@{{ .digest }}{{- else -}}{{ .repository }}:{{ .tag }}{{- end -}}
{{- end }}

{{- define "app.podSecurity" -}}
securityContext:
  runAsNonRoot: true
  runAsUser: 10001
  runAsGroup: 10001
  fsGroup: 10001
  seccompProfile: { type: RuntimeDefault }
{{- end }}

{{- define "app.containerSecurity" -}}
securityContext:
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  capabilities: { drop: ["ALL"] }
{{- end }}

{{/*
Keys that only the chart may set (ADR-0039, RT2-08): the environment, the database connection, the trusted proxies and
every limit of the api (the Settings fields of backend/app/config.py). pydantic-settings reads variables without regard
to case, so the match ignores case. values.schema.json forbids the same keys; this fails with the key named.
*/}}
{{- define "app.env.forbidden" -}}
(?i)^APP_(ENVIRONMENT|DATABASE_.*|TRUSTED_PROXY_.*|.*_PER_.*|CODES_PER_HOUR|MAX_ATTEMPTS|RATE_.*|OPEN_LOGIN_.*|LIVE_.*|LOGIN_REQUESTS_.*|BODY_LIMIT_BYTES|CODE_TTL_SECONDS|RESEND_COOLDOWN_SECONDS|IDLE_SECONDS|ABSOLUTE_SECONDS)$
{{- end }}

{{- define "app.env.validate" -}}
{{- $pattern := include "app.env.forbidden" . -}}
{{- range $component := list "api" "web" -}}
{{- range $key := keys (default dict (index $.Values $component).env) | sortAlpha -}}
{{- if regexMatch $pattern $key -}}
{{- fail (printf "%s.env.%s is set by the chart or is a limit of the api; remove it from env (environment and config.* set the environment, trusted proxies and database)" $component $key) -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- end }}

{{/*
The environment of the api, from .Values.environment. Every chart environment runs the production rules of the api: the
Settings values development and test (docs on, weaker connection rules) exist for compose and CI, never for a cluster.
*/}}
{{- define "app.apiEnvironment" -}}
{{- $map := dict "local" "production" "staging" "production" "production" "production" -}}
{{- get $map .Values.environment | required (printf "environment must be local, staging or production, not %q" .Values.environment) -}}
{{- end }}
