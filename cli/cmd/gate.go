package cmd

import (
	"fmt"
	"os"

	"github.com/spf13/cobra"
)

// gate is the fallback path for GitLab non-Ultimate: CI job calls
//   crv gate check --pr 42
// and the exit code drives the pipeline.

func gateCmd() *cobra.Command {
	c := &cobra.Command{
		Use:   "gate",
		Short: "CI-side gate helpers",
	}
	c.AddCommand(gateCheckCmd())
	return c
}

func gateCheckCmd() *cobra.Command {
	var pr int
	c := &cobra.Command{
		Use:   "check",
		Short: "Exit 0 if the PR gate passes; exit 1 otherwise. For CI.",
		RunE: func(cmd *cobra.Command, args []string) error {
			// M4: GET {API}/api/v1/repos/{detected}/prs/{pr}/gate; parse decision.
			fmt.Fprintf(os.Stderr, "crv gate check --pr %d (implemented in M4)\n", pr)
			return nil
		},
	}
	c.Flags().IntVar(&pr, "pr", 0, "pull request number")
	_ = c.MarkFlagRequired("pr")
	return c
}
