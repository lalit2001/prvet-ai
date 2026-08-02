package cmd

import (
	"fmt"

	"github.com/spf13/cobra"
)

func airgapCmd() *cobra.Command {
	c := &cobra.Command{
		Use:   "airgap",
		Short: "Bundle and install for airgapped environments",
	}
	pack := &cobra.Command{
		Use:   "package",
		Short: "Download every image and bundle with the chart",
		RunE: func(cmd *cobra.Command, args []string) error {
			fmt.Println("crv airgap package (implemented in M6)")
			return nil
		},
	}
	install := &cobra.Command{
		Use:   "install <bundle>",
		Short: "Push images to an internal registry and helm install",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			fmt.Printf("crv airgap install %s (implemented in M6)\n", args[0])
			return nil
		},
	}
	c.AddCommand(pack, install)
	return c
}
