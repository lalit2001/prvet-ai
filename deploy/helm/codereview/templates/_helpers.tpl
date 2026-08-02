{{- define "crv.name" -}}crv{{- end -}}
{{- define "crv.fullname" -}}{{- printf "%s-%s" .Release.Name (include "crv.name" .) | trunc 63 | trimSuffix "-" -}}{{- end -}}
{{- define "crv.labels" -}}
app.kubernetes.io/name: {{ include "crv.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}
{{- define "crv.selectorLabels" -}}
app.kubernetes.io/name: {{ include "crv.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
