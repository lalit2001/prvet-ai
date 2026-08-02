package cmd

import (
	"bytes"
	"strings"
	"testing"
)

func TestRootMentionsUiOnly(t *testing.T) {
	buf := &bytes.Buffer{}
	root := Root()
	root.SetOut(buf)
	root.SetArgs([]string{"--help"})
	if err := root.Execute(); err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(buf.String(), "web UI") {
		t.Error("root help should tell users repo/LLM/rule config lives in the web UI")
	}
}
