package main

import (
	"fmt"
	"log"
	"net"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/bigkevmcd/go-configparser"
	"github.com/gosnmp/gosnmp"
	"github.com/spf13/cobra"
	"github.com/spf13/pflag"
	"github.com/spf13/viper"
)

var (
	defaultConfigFilename = "snmp_discovery"
	defaultIniSectionName = "snmp_discovery"
	CONFIGPATH            = "../conf.d"
	// TODO: Need to update the each case
	POWERSTORETYPE = "0"
	POWERSCALETYPE = "1"
	POWERFLEXTYPE  = "2"
	CONNECTIONKEY  = "connectionUrl"
)

type snmpInfo struct {
	Host     string `json:"host,omitempty" validate:"required"`
	PduName  string `json:"pduName,omitempty" validate:"required"`
	TypeName string `json:"typeName,omitempty" validate:"required"`
}

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

func handleWalkResult(host string, resultChan chan string) gosnmp.WalkFunc {
	return func(pdu gosnmp.SnmpPDU) error {
		// The string to be passed into the channel.
		var resString string
		// fmt.Printf("%s\t%s = ", host, pdu.Name)
		resString += host + ";" + pdu.Name + ";"
		switch pdu.Type {
		case gosnmp.OctetString:
			b := pdu.Value.([]byte)
			fmt.Printf("STRING: %s\n", string(b))
			resString += string(b)
		default:
			// fmt.Printf("TYPE %d: %d\n", pdu.Type, gosnmp.ToBigInt(pdu.Value))
			resString += fmt.Sprint(gosnmp.ToBigInt(pdu.Value))
			resultChan <- resString
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
				log.Printf("Failed to parse CIDR %s, will try to parse the input as IP address. error: %v", r, err)

				ipAddress := net.ParseIP(r)
				if ipAddress == nil {
					log.Output(1, "Failed to pass the IP address, ignore.")
				}
				hosts = append(hosts, ipAddress.String())
				continue
			}

			for ip := ipnet.IP.Mask(ipnet.Mask); ipnet.Contains(ip); inc(ip) {
				hosts = append(hosts, ip.String())
			}
		}
	}

	var wg sync.WaitGroup

	// Create a channel to receive SNMP results
	// resultChan := make(chan *gosnmp.SnmpPacket)
	resultChan := make(chan string)

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
				// fmt.Printf("[ERROR] SNMP connect failed at %s:%v, error: %v\n", host, port, err)
				return
			}

			defer func(Conn net.Conn) {
				Conn.Close()
			}(gs.Conn)
			log.Output(1, "Processing the host: "+host)
			err = gs.BulkWalk(oid, handleWalkResult(host, resultChan))
			if err != nil {
				// fmt.Printf("[ERROR] SNMP walk failed at %s:%v, error: %v\n", host, port, err)
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
		updateConfigBasedOnSNPM(result)
	}
}

func updateConfigBasedOnSNPM(result string) {
	items := strings.Split(result, ";")
	snmp := snmpInfo{
		Host:     items[0],
		PduName:  items[1],
		TypeName: items[2],
	}
	configPaths := getConfigFiles(CONFIGPATH)
	var powerFlexParser []string
	var powerStoreParser []string
	var powerScaleParser []string
	for _, path := range configPaths {
		p, err := configparser.NewConfigParserFromFile(path)
		if err != nil {
			panic(err)
		}
		for _, v := range p.Sections() {
			switch v {
			case "powerFlex":
				powerFlexParser = append(powerFlexParser, path)
			case "powerScale":
				powerScaleParser = append(powerScaleParser, path)
			case "powerStore":
				powerStoreParser = append(powerStoreParser, path)
			}
		}
	}

	switch snmp.TypeName {
	// Update the configuration file according to the instance type
	case POWERFLEXTYPE:
		if len(powerFlexParser) != 0 {
			updateConnectionURL(snmp.Host, powerFlexParser)
		}
	case POWERSCALETYPE:
		if len(powerScaleParser) != 0 {
			updateConnectionURL(snmp.Host, powerScaleParser)
		}

	case POWERSTORETYPE:
		if len(powerStoreParser) != 0 {
			updateConnectionURL(snmp.Host, powerStoreParser)
		}
	}
}

func updateConnectionURL(host string, configPath []string) {
	for _, path := range configPath {
		p, err := configparser.NewConfigParserFromFile(path)
		if err != nil {
			panic(err)
		}
		for _, sec := range p.Sections() {
			switch sec {
			case "insightfinder":
				continue
			default:
				// Update the section other than IF.
				curVal, err := p.Get(sec, CONNECTIONKEY)
				urls := parseURLList(curVal)
				if contains(urls, host) {
					break
				}
				if err != nil {
					panic(err)
				}
				p.Set(sec, CONNECTIONKEY, curVal+","+host)
			}
		}
		p.SaveWithDelimiter(path, "=")
	}
}

func parseURLList(input string) []string {
	urls := strings.Split(input, ",")
	return Map(urls, strings.TrimSpace)
}
func Map(vs []string, f func(string) string) []string {
	vsm := make([]string, len(vs))
	for i, v := range vs {
		vsm[i] = f(v)
	}
	return vsm
}

func contains(s []string, e string) bool {
	for _, a := range s {
		if a == e {
			return true
		}
	}
	return false
}

func absFilePath(filename string) string {
	if filename == "" {
		filename = ""
	}
	curdir, err := os.Getwd()
	if err != nil {
		panic(err)
	}
	mydir, err := filepath.Abs(curdir)
	if err != nil {
		panic(err)
	}
	return filepath.Join(mydir, filename)
}

func getConfigFiles(configRelativePath string) []string {
	if configRelativePath == "" {
		// default value for configuration path
		configRelativePath = "conf.d"
	}
	configPath := absFilePath(configRelativePath)
	log.Output(2, "Reading config files from directory: "+configPath)
	allConfigs, err := filepath.Glob(configPath + "/*.ini")
	if err != nil {
		panic(err)
	}
	if len(allConfigs) == 0 {
		panic("[ERROR] No config file found in" + configPath)
	}
	return allConfigs
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
