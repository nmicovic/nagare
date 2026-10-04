package picker

import (
	"testing"

	tea "charm.land/bubbletea/v2"

	"github.com/nmicovic/nagare/internal/models"
)

func TestRenamePrefillOmitsSessionPrefix(t *testing.T) {
	sessions := []models.Session{
		{Name: "harbor-platform-frontend/klaudije", SessionName: "harbor-platform-frontend", WindowIndex: 0},
		{Name: "harbor-platform-frontend/omp_01", SessionName: "harbor-platform-frontend", WindowIndex: 1},
	}
	m := NewForTest()
	m.sessions = sessions
	m.filtered = sessions

	m = driveModel(t, m, tea.KeyPressMsg{Code: tea.KeyF2})

	if !m.renameMode {
		t.Fatal("F2 did not enter rename mode")
	}
	if got := m.searchInput.Value(); got != "klaudije" {
		t.Errorf("rename prefill = %q, want %q", got, "klaudije")
	}
}

func TestRenameWindowNameStripsDisplayPrefix(t *testing.T) {
	session := models.Session{SessionName: "harbor-platform-frontend"}
	tests := []struct {
		name  string
		value string
		want  string
	}{
		{"qualified display name", "harbor-platform-frontend/reviewer", "reviewer"},
		{"bare window name", "reviewer", "reviewer"},
		{"surrounding whitespace", " harbor-platform-frontend/reviewer ", "reviewer"},
		{"different prefix", "harbor-platform-backend/reviewer", "harbor-platform-backend/reviewer"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := renameWindowName(session, tt.value); got != tt.want {
				t.Errorf("renameWindowName() = %q, want %q", got, tt.want)
			}
		})
	}
}
