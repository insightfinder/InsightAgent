package main

import (
	"fmt"
	"github.com/gosnmp/gosnmp"
	"github.com/spf13/cobra"
	"github.com/spf13/pflag"
	"github.com/spf13/viper"
	"log"
	"net"
	"os"
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

func inc(ip net.IP) {
	for j := len(ip) - 1; j >= 0; j-- {
		ip[j]++
		if ip[j] > 0 {
			break
		}
	}
}

func handleWalkResult(host string) gosnmp.WalkFunc {
	return func(pdu gosnmp.SnmpPDU) error {

		// TODO: fix the result
		fmt.Printf("%s\t%s = ", host, pdu.Name)

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
	// Use nmap to scan the network for hosts with the specified port open
	//hosts := nmapScan(ipRange, port)
	ranges := strings.Split(ipRange, " ")
	hosts := make([]string, 0)

	for _, r := range ranges {
		if len(strings.TrimSpace(r)) > 0 {
			_, ipnet, err := net.ParseCIDR(r)
			if err != nil {
				log.Printf("Failed to parse CIDR %s, ignored. error: %v", r, err)
			}

			for ip := ipnet.IP.Mask(ipnet.Mask); ipnet.Contains(ip); inc(ip) {
				hosts = append(hosts, ip.String())
			}
		}
	}

	var wg sync.WaitGroup

	// Create a channel to receive SNMP results
	resultChan := make(chan *gosnmp.SnmpPacket)

	// Use the results to print an example output
	for _, host := range hosts {

		wg.Add(1)

		host := host
		go func() {
			defer wg.Done()

			gs := &gosnmp.GoSNMP{
				Target:    host,
				Port:      uint16(port),
				Community: community,
				Version:   gosnmp.Version2c,
				Timeout:   time.Duration(5) * time.Second,
			}
			err := gs.Connect()
			if err != nil {
				fmt.Printf("snmp connect failed at %s:%v, error: %v\n", host, port, err)
				resultChan <- nil
				return
			}

			defer func(Conn net.Conn) {
				err := Conn.Close()
				if err != nil {
					// ignore close error
				}
			}(gs.Conn)

			err = gs.BulkWalk(oid, handleWalkResult(host))
			if err != nil {
				//fmt.Printf("snmp walk failed at %s:%v, error: %v\n", host, port, err)
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
