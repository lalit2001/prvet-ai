package cmd

import (
	"fmt"

	"github.com/spf13/cobra"
)

func initCmd() *cobra.Command {
	var nonInteractive bool
	c := &cobra.Command{
		Use:   "init",
		Short: "One-time bootstrap: choose target, write .env or crv.config.yaml",
		RunE: func(cmd *cobra.Command, args []string) error {
			// M0: minimal stub. Full TUI wizard lands with M5.
			fmt.Println("crv init: writes .env or crv.config.yaml for the chosen target")
			fmt.Println("(interactive TUI wizard implemented in M5; non-interactive flag ready)")
			_ = nonInteractive
			return nil
		},
	}
	c.Flags().BoolVar(&nonInteractive, "non-interactive", false, "skip prompts; require flags/env for everything")
	return c
}
