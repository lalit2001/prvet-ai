package cmd

import (
	"fmt"

	"github.com/spf13/cobra"
)

func deployCmd() *cobra.Command {
	var target string
	c := &cobra.Command{
		Use:   "deploy",
		Short: "Provision & bring up the stack on the chosen target",
		RunE: func(cmd *cobra.Command, args []string) error {
			// M5: dispatch to embed/compose | embed/terraform/{aws,azure,gcp} | embed/helm.
			fmt.Printf("crv deploy --target %s (implemented in M5)\n", target)
			return nil
		},
	}
	c.Flags().StringVar(&target, "target", "compose", "compose|aws|azure|k8s")
	return c
}

func destroyCmd() *cobra.Command {
	var target string
	c := &cobra.Command{
		Use:   "destroy",
		Short: "Tear down the deployed stack",
		RunE: func(cmd *cobra.Command, args []string) error {
			fmt.Printf("crv destroy --target %s (implemented in M5)\n", target)
			return nil
		},
	}
	c.Flags().StringVar(&target, "target", "compose", "compose|aws|azure|k8s")
	return c
}
