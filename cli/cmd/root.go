package cmd

import "github.com/spf13/cobra"

func Root() *cobra.Command {
	root := &cobra.Command{
		Use:   "prvet",
		Short: "PRVet deployment helper",
		Long: `prvet is the deploy-only CLI for PRVet.

It provisions and upgrades the platform. Everything else — connecting forges,
enabling repos, configuring LLMs, editing rules, setting thresholds, viewing
findings and reports — happens in the web UI.`,
	}
	root.AddCommand(initCmd(), deployCmd(), destroyCmd(), doctorCmd(), gateCmd(), airgapCmd(), versionCmd())
	return root
}
