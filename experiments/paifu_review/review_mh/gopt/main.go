// 원본 CalcPoint 직접 호출: 화료 손(JSON 한 줄) → 점수·판·부·역
package main

import (
	"encoding/json"
	"fmt"
	"os"

	"github.com/EndlessCheng/mahjong-helper/util"
	"github.com/EndlessCheng/mahjong-helper/util/model"
)

type in struct {
	Hand34   []int    `json:"hand34"`
	Melds    []struct{ Type string; Tiles []int } `json:"melds"`
	Dora     []int    `json:"dora_tiles"`
	Red      []int    `json:"red_fives"`
	Round    int      `json:"round_wind"`
	Self     int      `json:"self_wind"`
	Parent   bool     `json:"is_parent"`
	Win      int      `json:"win"`
	Tsumo    bool     `json:"tsumo"`
	Riichi   bool     `json:"riichi"`
}

func main() {
	var xs []in
	b, _ := os.ReadFile(os.Args[1])
	json.Unmarshal(b, &xs)
	out := []interface{}{}
	for _, x := range xs {
		melds := []model.Meld{}
		for _, m := range x.Melds {
			t := map[string]int{"chi": model.MeldTypeChi, "pon": model.MeldTypePon, "ankan": model.MeldTypeAnkan, "minkan": model.MeldTypeMinkan}[m.Type]
			melds = append(melds, model.Meld{MeldType: t, Tiles: m.Tiles})
		}
		pi := &model.PlayerInfo{HandTiles34: x.Hand34, Melds: melds, DoraTiles: x.Dora, NumRedFives: x.Red,
			RoundWindTile: x.Round, SelfWindTile: x.Self, IsParent: x.Parent, WinTile: x.Win, IsTsumo: x.Tsumo, IsRiichi: x.Riichi}
		r := util.CalcPoint(pi)
		out = append(out, map[string]interface{}{"point": r.Point, "s": fmt.Sprint(r)})
	}
	o, _ := json.Marshal(out)
	os.Stdout.Write(o)
}
