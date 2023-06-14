package main

import (
	"context"
	"fmt"
	"github.com/Ullaakut/nmap/v3"
	"github.com/gosnmp/gosnmp"
	"github.com/spf13/cobra"
	"github.com/spf13/pflag"
	"github.com/spf13/viper"
	"log"
	"net"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"
)

var (
	defaultConfigFilename = "snmp_discovery"
	defaultIniSectionName = "snmp_discovery"
)

func main() {
	cmd := NewRootCommand()
	if err := cmd.Execute(); err != nil {
		os.Exit(1)
	}
}

type SnmpPort struct {
	host string
	port nmap.Port
}

func nmapScan(ipRange string, port int) []SnmpPort {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)
	defer cancel()

	ranges := strings.Split(ipRange, ",")
	// Set up Nmap scanner
	scanner, err := nmap.NewScanner(
		ctx,
		nmap.WithTargets(ranges...),
		nmap.WithPorts(strconv.Itoa(port)),
	)
	if err != nil {
		log.Fatalf("Failed to create nmap scanner: %v", err)
	}

	// Executes asynchronously, allowing results to be streamed in real time.
	done := make(chan error)
	result, warnings, err := scanner.Async(done).Run()
	if err != nil {
		log.Fatal(err)
	}

	// Blocks main until the scan has completed.
	if err := <-done; err != nil {
		if len(*warnings) > 0 {
			log.Printf("run finished with warnings: %s\n", *warnings)
		}
		log.Fatal(err)
	}

	var ports []SnmpPort

	for _, host := range result.Hosts {
		if len(host.Ports) == 0 || len(host.Addresses) == 0 {
			continue
		}

		fmt.Printf("Host %q:\n", host.Addresses[0])

		for _, port := range host.Ports {
			if port.State.State != "open" {
				fmt.Printf("\tPort %d/%s %s %s\n", port.ID, port.Protocol, port.State, port.Service.Name)
			} else {
				ports = append(ports, SnmpPort{host: host.Addresses[0].String(), port: port})
			}
		}
	}

	return ports
}

func handleWalkResult(host string) gosnmp.WalkFunc {
	return func(pdu gosnmp.SnmpPDU) error {

		// TODO:
		fmt.Printf("%s = ", pdu.Name)

		switch pdu.Type {
		case gosnmp.OctetString:
			b := pdu.Value.([]byte)
			fmt.Printf("STRING: %s\n", string(b))
		default:
			fmt.Printf("TYPE %d: %d\n", pdu.Type, gosnmp.ToBigInt(pdu.Value))
		}
		return nil
	}
}

func snmpDiscovery(ipRange string, port int, community string, oid string) {
	snmpPorts := nmapScan(ipRange, port)

	var wg sync.WaitGroup

	// Create a channel to receive SNMP results
	resultChan := make(chan *gosnmp.SnmpPacket)

	// Use the results to print an example output
	for _, snmpPort := range snmpPorts {

		wg.Add(1)
		snmpPort := snmpPort

		go func() {
			defer wg.Done()

			gs := &gosnmp.GoSNMP{
				Target:    snmpPort.host,
				Port:      snmpPort.port.ID,
				Community: community,
				Version:   gosnmp.Version2c,
				Timeout:   time.Duration(5) * time.Second,
			}
			err := gs.Connect()
			if err != nil {
				fmt.Printf("snmp connect failed at %s:%v, error: %v\n", snmpPort.host, snmpPort.port.ID, err)
				resultChan <- nil
				return
			}

			defer func(Conn net.Conn) {
				err := Conn.Close()
				if err != nil {
					// ignore close error
				}
			}(gs.Conn)

			err = gs.BulkWalk(oid, handleWalkResult(snmpPort.host))
			if err != nil {
				fmt.Printf("snmp walk failed at %s:%v, error: %v\n", snmpPort.host, snmpPort.port.ID, err)
				resultChan <- nil
				return
			}
		}()
	}

	// Wait for all goroutines to finish
	go func() {
		wg.Wait()
		close(resultChan)
	}()

	// Process SNMP results
	for result := range resultChan {
		if result == nil {
			continue
		}

		// Process the response
		if result.Error > 0 {
			log.Printf("Error response received: %v", result.Error)
		} else {
			for _, pdu := range result.Variables {
				fmt.Printf("OID: %s, Value: %s\n", pdu.Name, pdu.Value)
			}
		}
	}
}

func NewRootCommand() *cobra.Command {

	ipRange := ""
	community := ""
	oid := ""
	port := 0

	rootCmd := &cobra.Command{
		Use:   "snmp_discovery",
		Short: "SNMP Discovery",
		PersistentPreRunE: func(cmd *cobra.Command, args []string) error {
			return initializeConfig(cmd)
		}, Run: func(cmd *cobra.Command, args []string) {

			println("snmp discovery with ip range:", ipRange, ",community:", community, ",oid:", oid, ",port:", port)
			snmpDiscovery(ipRange, port, community, oid)
		},
	}

	rootCmd.Flags().StringVarP(&ipRange, "ip-range", "", "", "ip range to discover the devices")
	rootCmd.Flags().StringVarP(&community, "community", "c", "public", "What is the community string?")
	rootCmd.Flags().StringVarP(&oid, "oid", "o", "", "the mid/oid defining a subtree of values, split by commas")
	rootCmd.Flags().IntVarP(&port, "port", "p", 161, "the port to use for the SNMP connection")

	return rootCmd
}

func initializeConfig(cmd *cobra.Command) error {
	v := viper.New()

	v.SetConfigName(defaultConfigFilename)
	v.SetConfigType("ini")
	v.AddConfigPath(".")

	if err := v.ReadInConfig(); err != nil {
		// It's okay if the config file doesn't exist
		if _, ok := err.(viper.ConfigFileNotFoundError); !ok {
			return err
		}
	}

	bindFlags(cmd, v)
	return nil
}

func bindFlags(cmd *cobra.Command, v *viper.Viper) {
	cmd.Flags().VisitAll(func(f *pflag.Flag) {
		configName := f.Name

		if !f.Changed && (v.IsSet(configName) || v.IsSet(defaultIniSectionName+"."+configName)) {
			val := v.Get(configName)
			if val == nil {
				val = v.Get(defaultIniSectionName + "." + configName)
			}
			_ = cmd.Flags().Set(f.Name, val.(string))
		}
	})
}
