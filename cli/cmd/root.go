package cmd

import "github.com/spf13/cobra"

func Root() *cobra.Command {
	root := &cobra.Command{
		Use:   "crv",
		Short: "Sentry Review deployment helper",
		Long: `crv is the deploy-only CLI for Sentry Review.

It provisions and upgrades the platform. Everything else — connecting forges,
enabling repos, configuring LLMs, editing rules, setting thresholds, viewing
findings and reports — happens in the web UI.`,
	}
	root.AddCommand(initCmd(), deployCmd(), destroyCmd(), doctorCmd(), gateCmd(), airgapCmd(), versionCmd())
	return root
}
