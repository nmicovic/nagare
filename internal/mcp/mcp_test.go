package mcp

import (
	"path/filepath"
	"strings"
	"testing"
)

func TestInboxDirSanitizesSlashes(t *testing.T) {
	got := InboxDir("acme-api/claude_01")
	if strings.Contains(filepath.Base(got), "/") {
		t.Errorf("InboxDir leaked slash into directory component: %q", got)
	}
	if filepath.Base(got) != "acme-api__claude_01" {
		t.Errorf("got %q, want ...acme-api__claude_01", got)
	}
}
