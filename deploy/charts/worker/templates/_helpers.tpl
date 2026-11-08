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

{{- define "worker.probe" -}}
exec:
  command:
    - python
    - -c
    - import os, sys, time; sys.exit(0 if time.time() - os.path.getmtime('{{ .Values.heartbeat.path }}') < {{ .Values.heartbeat.maxAgeSeconds }} else 1)
{{- end }}
