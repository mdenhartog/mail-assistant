{{- define "component.name" -}}
{{- default .Release.Name .Values.nameOverride | trunc 52 | trimSuffix "-" -}}
{{- end }}

{{- define "component.labels" -}}
app.kubernetes.io/name: {{ include "component.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/part-of: {{ .Chart.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "component.selector" -}}
app.kubernetes.io/name: {{ include "component.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "component.image" -}}
{{- if .Values.image.digest -}}{{ .Values.image.repository }}@{{ .Values.image.digest }}{{- else -}}{{ .Values.image.repository }}:{{ .Values.image.tag }}{{- end -}}
{{- end }}
