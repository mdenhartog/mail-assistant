{{- define "worker.name" -}}
{{- default .Release.Name .Values.nameOverride | trunc 52 | trimSuffix "-" -}}
{{- end }}

{{- define "worker.labels" -}}
app.kubernetes.io/name: {{ include "worker.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/part-of: {{ .Chart.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "worker.selector" -}}
app.kubernetes.io/name: {{ include "worker.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "worker.image" -}}
{{- if .Values.image.digest -}}{{ .Values.image.repository }}@{{ .Values.image.digest }}{{- else -}}{{ .Values.image.repository }}:{{ .Values.image.tag }}{{- end -}}
{{- end }}

{{- define "worker.migrationName" -}}
{{- printf "%s-migrate" (include "worker.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end }}

{{- define "worker.migrationSelector" -}}
app.kubernetes.io/name: {{ include "worker.migrationName" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "worker.probe" -}}
exec:
  command:
    - python
    - -c
    - import os, sys, time; sys.exit(0 if time.time() - os.path.getmtime('{{ .Values.heartbeat.path }}') < {{ .Values.heartbeat.maxAgeSeconds }} else 1)
{{- end }}

{{/*
Keys that only the chart may set (SEC3-08): the environment, every DATABASE_* variable (the chart writes DATABASE_SSL,
DATABASE_CA_FILE and, in the migration Job, DATABASE_OWNER_URL; the worker's DATABASE_URL comes from envFromSecret) and
the role passwords of the migration Job. The agent reads variables without regard to case and the last duplicate wins,
so the match ignores case. values.schema.json forbids the same keys.
*/}}
{{- define "worker.env.forbidden" -}}
(?i)^(ENVIRONMENT|DATABASE_.*|RUNTIME_ROLE_PASSWORD|WEB_ROLE_PASSWORD)$
{{- end }}

{{/* Database TLS (SEC-10, W-8, W-9): the same three settings for the worker and the migration Job. */}}
{{- define "worker.dbTls.validate" -}}
{{- include "worker.required.validate" . -}}
{{- $tls := .Values.database.tls -}}
{{- if not (has $tls.sslMode (list "disable" "require" "verify-ca" "verify-full")) -}}
{{- fail "database.tls.sslMode must be one of disable, require, verify-ca, verify-full" -}}
{{- end -}}
{{- if and (eq .Values.environment "production") (ne $tls.sslMode "verify-full") -}}
{{- fail "database.tls.sslMode must be verify-full when environment is production" -}}
{{- end -}}
{{- if and (has $tls.sslMode (list "verify-ca" "verify-full")) (not $tls.caConfigMap) -}}
{{- fail "database.tls.caConfigMap is required for verify-ca and verify-full (name of a ConfigMap with the key ca.crt)" -}}
{{- end -}}
{{- range $key := keys (default dict .Values.env) | sortAlpha -}}
{{- if regexMatch (include "worker.env.forbidden" $) $key -}}
{{- fail (printf "env.%s is set by the chart (environment, database.tls and the migration Secret); remove it from env" $key) -}}
{{- end -}}
{{- end -}}
{{- end }}

{{- define "worker.dbTls.env" -}}
{{- include "worker.dbTls.validate" . -}}
- { name: ENVIRONMENT, value: {{ .Values.environment | quote }} }
- { name: DATABASE_SSL, value: {{ .Values.database.tls.sslMode | quote }} }
{{- if .Values.database.tls.caConfigMap }}
- { name: DATABASE_CA_FILE, value: {{ printf "%s/ca.crt" .Values.database.tls.caMountPath | quote }} }
{{- end }}
{{- end }}

{{- define "worker.dbTls.mount" -}}
{{- if .Values.database.tls.caConfigMap -}}
- { name: db-ca, mountPath: {{ .Values.database.tls.caMountPath | quote }}, readOnly: true }
{{- end -}}
{{- end }}

{{- define "worker.dbTls.volume" -}}
{{- if .Values.database.tls.caConfigMap -}}
- name: db-ca
  configMap:
    name: {{ .Values.database.tls.caConfigMap | quote }}
    items:
      - { key: ca.crt, path: ca.crt }
{{- end -}}
{{- end }}

{{/* Names the environment must supply carry the sentinel REQUIRED in deploy/envs/<env>/mail-triage.yaml; the render stops and names the value. */}}
{{- define "worker.required.validate" -}}
{{- range $path, $value := dict "envFromSecret" .Values.envFromSecret "database.tls.caConfigMap" .Values.database.tls.caConfigMap "migration.secretName" .Values.migration.secretName -}}
{{- if eq (toString $value) "REQUIRED" -}}
{{- fail (printf "%s is REQUIRED: supply it in the environment values (it is still the sentinel)" $path) -}}
{{- end -}}
{{- end -}}
{{- end }}
