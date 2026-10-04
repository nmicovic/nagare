package bin

import (
	"os"
	"os/exec"
)

// FindSelf locates the nagare binary path.
func FindSelf() string {
	if path, err := exec.LookPath("nagare"); err == nil {
		return path
	}
	if exe, err := os.Executable(); err == nil {
		return exe
	}
	return "nagare"
}
