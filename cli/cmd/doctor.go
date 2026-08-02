package cmd

import (
	"fmt"

	"github.com/spf13/cobra"
)

func doctorCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "doctor",
		Short: "Probe DB, queue, storage, LLM, forge auth",
		RunE: func(cmd *cobra.Command, args []string) error {
			// M1: probe /readyz on the API URL from crv.config.yaml or .env; print colored table.
			fmt.Println("crv doctor: probing dependencies (implemented in M1)")
			return nil
		},
	}
}
