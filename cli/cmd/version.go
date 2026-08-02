package cmd

import (
	"fmt"

	"github.com/spf13/cobra"
)

// Set at build time via -ldflags "-X github.com/sentry-review/crv/cmd.Version=..."
var Version = "0.1.0-dev"

func versionCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "version",
		Short: "Print crv version",
		Run: func(cmd *cobra.Command, args []string) {
			fmt.Println(Version)
		},
	}
}
