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
Keys that only the chart may set (ADR-0039, RT2-08, RT3-06): the environment, the database connection, the trusted
proxies, every limit of the api (the Settings fields of backend/app/config.py) and every variable the chart writes itself
in workloads.yaml, plain (the config.* values) and secret (the secretKeyRef list). pydantic-settings reads variables
without regard to case and the last duplicate wins, so the match ignores case. values.schema.json forbids the same
keys; this fails with the key named. A key added to workloads.yaml belongs in this list (a test compares both).
*/}}
{{- define "app.env.forbidden" -}}
(?i)^APP_(ENVIRONMENT|DATABASE_.*|TRUSTED_PROXY_.*|.*_PER_.*|CODES_PER_HOUR|MAX_ATTEMPTS|RATE_.*|OPEN_LOGIN_.*|LIVE_.*|LOGIN_REQUESTS_.*|BODY_LIMIT_BYTES|CODE_TTL_SECONDS|RESEND_COOLDOWN_SECONDS|IDLE_SECONDS|ABSOLUTE_SECONDS|USERNAME|EMAIL_ADDRESS|SMTP_HOST|SMTP_PORT|SMTP_FROM|PUBLIC_ORIGIN|NOTICE_INTERVAL_MINUTES|CODE_HASH_KEY|CSRF_KEY|USERNAME_HASH_KEY|SMTP_USER|SMTP_PASSWORD)$
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

{{/*
Values that an environment must supply carry the sentinel REQUIRED in deploy/envs/<env>/values.yaml. A string that is
still the sentinel stops the render and names the value. Typed values (digests, ports, addresses) are refused by
values.schema.json with the same path.
*/}}
{{- define "app.required.validate" -}}
{{- range $path := list "api.config.username" "api.config.emailAddress" "api.config.publicOrigin" "api.config.smtp.host" "api.config.smtp.from" "ingress.host" "ingress.clusterIssuer" -}}
{{- $node := $.Values.AsMap -}}
{{- range $part := splitList "." $path -}}
{{- if kindIs "map" $node -}}{{- $node = get $node $part -}}{{- end -}}
{{- end -}}
{{- if eq (toString $node) "REQUIRED" -}}
{{- fail (printf "%s is REQUIRED: supply it in the environment values (it is still the sentinel)" $path) -}}
{{- end -}}
{{- end -}}
{{- end }}
