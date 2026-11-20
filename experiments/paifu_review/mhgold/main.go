// 원본 mahjong-helper 의 버림 평가를 mh_cases.json 입력으로 돌려 JSON 으로 낸다.
package main

import (
	"encoding/json"
	"math"
	"os"
	"sort"
	"strconv"

	"github.com/EndlessCheng/mahjong-helper/util"
	"github.com/EndlessCheng/mahjong-helper/util/model"
)

type meldIn struct {
	Type  string `json:"type"`
	Tiles []int  `json:"tiles"`
}
type input struct {
	Hand34    []int    `json:"hand34"`
	Melds     []meldIn `json:"melds"`
	DoraTiles []int    `json:"dora_tiles"`
	RedFives  []int    `json:"red_fives"`
	Left34    []int    `json:"left34"`
	Discards  []int    `json:"discards"`
	Round     int      `json:"round_wind"`
	Self      int      `json:"self_wind"`
	IsParent  bool     `json:"is_parent"`
}
type caseIn struct {
	ID    string `json:"id"`
	Input input  `json:"input"`
}

func f(v float64) interface{} {
	if math.IsNaN(v) || math.IsInf(v, 0) {
		return nil
	}
	return v
}

func one(r *util.Hand14AnalysisResult) map[string]interface{} {
	r13 := r.Result13
	waits := map[string]int{}
	for t, c := range r13.Waits {
		waits[strconv.Itoa(t)] = c
	}
	return map[string]interface{}{
		"tile": r.DiscardTile, "shanten": r13.Shanten, "waits": waits,
		"waits_count": r13.Waits.AllCount(), "avg_improve": f(r13.AvgImproveWaitsCount),
		"improve_kinds": len(r13.Improves), "improve_way": r13.ImproveWayCount,
		"avg_next": f(r13.AvgNextShantenWaitsCount), "speed": f(r13.MixedWaitsScore),
		"agari_rate": f(r13.AvgAgariRate), "dama": f(r13.DamaPoint), "riichi": f(r13.RiichiPoint),
		"round_point": f(r13.MixedRoundPoint), "furiten_rate": r13.FuritenRate,
		"is_part_wait": r13.IsPartWait, "dora_count": r13.DoraCount,
	}
}

func main() {
	raw, err := os.ReadFile(os.Args[1])
	if err != nil {
		panic(err)
	}
	var doc struct {
		Cases []caseIn `json:"cases"`
	}
	if err := json.Unmarshal(raw, &doc); err != nil {
		panic(err)
	}
	out := map[string]interface{}{}
	for _, c := range doc.Cases {
		in := c.Input
		melds := []model.Meld{}
		for _, m := range in.Melds {
			t := map[string]int{"chi": model.MeldTypeChi, "pon": model.MeldTypePon, "ankan": model.MeldTypeAnkan, "minkan": model.MeldTypeMinkan}[m.Type]
			melds = append(melds, model.Meld{MeldType: t, Tiles: append([]int{}, m.Tiles...)})
		}
		pi := &model.PlayerInfo{
			HandTiles34:   append([]int{}, in.Hand34...),
			Melds:         melds,
			DoraTiles:     append([]int{}, in.DoraTiles...),
			NumRedFives:   append([]int{}, in.RedFives...),
			RoundWindTile: in.Round,
			SelfWindTile:  in.Self,
			IsParent:      in.IsParent,
			DiscardTiles:  append([]int{}, in.Discards...),
			LeftTiles34:   append([]int{}, in.Left34...),
		}
		shanten, results, inc := util.CalculateShantenWithImproves14(pi)
		// analysis.go simpleBestDiscardTile
		best := -1
		if len(results) > 0 {
			best = results[0].DiscardTile
		} else if len(inc) > 0 {
			best = inc[0].DiscardTile
		}
		rec := false
		if shanten == 1 && len(pi.DiscardTiles) < 9 && len(results) > 0 && len(inc) > 0 && !pi.IsNaki() {
			if results[0].Result13.Waits.AllCount() < 9 && results[0].Result13.MixedWaitsScore < inc[0].Result13.MixedWaitsScore {
				best = inc[0].DiscardTile
				rec = true
			}
		}
		fw, bw := []interface{}{}, []interface{}{}
		for _, r := range results {
			fw = append(fw, one(r))
		}
		for _, r := range inc {
			bw = append(bw, one(r))
		}
		var bestV interface{} = best
		if best < 0 {
			bestV = nil
		}
		out[c.ID] = map[string]interface{}{"shanten": shanten, "best": bestV, "recommend_backward": rec, "forward": fw, "backward": bw}
	}
	keys := []string{}
	for k := range out {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	b, _ := json.MarshalIndent(out, "", " ")
	os.Stdout.Write(b)
}
